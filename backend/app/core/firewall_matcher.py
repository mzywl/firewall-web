from typing import Optional, List, Dict, Tuple
import ipaddress
from sqlalchemy.orm import Session
import logging

# 导入模型
from app.models import Firewall, FirewallZone, Policy

logger = logging.getLogger(__name__)

NOT_PUSHED_REASONS = {
    'SAME_FIREWALL_NOT_ALLOWED': '源目的IP均在同一防火墙内部，未启用同墙推送',
    'NO_FIREWALL_MATCH': '未匹配到任何防火墙（IP资产未命中）',
    'NAT_CONFIG_MISSING': 'NAT配置缺失',
    'CROSS_ZONE_NO_NAT': '跨区域策略但无NAT规则'
}


class FirewallMatcher:
    """防火墙智能匹配器 (纯 IP 资产维增强版) — 对齐 重构.md §1 新设计

    新设计调整 (2026-06-22):
      - firewall.local_zone_name / external_zone_name / internal_protected_ips /
        external_protected_ips 已删除
      - 改用 FirewallZone.connect_region 跟 firewall.belong_region 对比判定
        internal/external
      - allow_same_firewall_push 字段已删除, 同墙推送默认允许
    """

    def __init__(self, db: Session):
        self.db = db

    def match_by_policy_context(self, policy: Policy) -> List[Dict]:
        """
        核心匹配接口: 完全基于【源IP、目的IP】精准匹配防火墙
        (已废弃原有的 ZoneAccessConfig 区域矩阵名称匹配)
        """
        logger.info(f"策略ID {policy.id}: 开始通过 [FirewallZone / IP网络资产] 进行归属判定... "
                    f"(Src: {policy.source_ip} -> Dst: {policy.dest_ip})")

        return self._match_by_ip_assets(policy)

    # ============================================================
    #                      IP 资产精准匹配核心
    # ============================================================

    def _match_by_ip_assets(self, policy: Policy) -> List[Dict]:
        """利用 FirewallZone 的网段资产进行全表扫描匹配 (新设计: 不再有 internal/external 文本字段)"""
        matched_results = []
        src_ip_obj = self._parse_to_ip_object(policy.source_ip, "源IP")
        dst_ip_obj = self._parse_to_ip_object(policy.dest_ip, "目的IP")

        if not src_ip_obj and not dst_ip_obj:
            return []

        # 捞出所有启用的防火墙
        all_firewalls = self.db.query(Firewall).filter(Firewall.is_active == 1).all()

        for fw in all_firewalls:
            # 1. 优先查 FirewallZone 细分区域
            fw_src_zone, src_zone_obj = self._find_zone_by_ip(src_ip_obj, fw)
            fw_dst_zone, dst_zone_obj = self._find_zone_by_ip(dst_ip_obj, fw)

            # internal/external 判定: 用 FirewallZone.connect_region 跟 firewall.belong_region 对比
            src_is_internal = self._is_zone_internal(src_zone_obj, fw)
            dst_is_internal = self._is_zone_internal(dst_zone_obj, fw)

            # fallback zone name (zone 没命中时)
            fallback_internal_zone = self._get_fallback_zone_name(fw, internal=True)
            fallback_external_zone = self._get_fallback_zone_name(fw, internal=False)

            # 2. 核心方向与归属判定逻辑 (纯 IP 增强型拓扑判定)
            # 如果这台防火墙连源 IP 和目的 IP 都不认识, 说明流量不经过它
            if not fw_src_zone and not fw_dst_zone:
                continue

            direction = None

            # 情况 A: 源和目的都在该墙资产内被识别
            if fw_src_zone and fw_dst_zone:
                if fw_src_zone == fw_dst_zone and src_is_internal:
                    direction = 'same_firewall'
                elif src_is_internal and not dst_is_internal:
                    direction = 'outbound'
                elif not src_is_internal and dst_is_internal:
                    direction = 'inbound'
                else:
                    direction = 'outbound'  # 跨外部区域默认出向

            # 情况 B: 只有源 IP 属于该墙内网, 目的 IP 是外部未知网段 (常规出向流量)
            elif src_is_internal:
                direction = 'outbound'
                fw_dst_zone = fallback_external_zone

            # 情况 C: 只有目的 IP 属于该墙内网, 源 IP 是外部未知网段 (常规入向流量)
            elif dst_is_internal:
                direction = 'inbound'
                fw_src_zone = fallback_external_zone

            else:
                # 识别出的 IP 都在外网, 未知内网归属, 安全起见略过这台墙
                continue

            if direction:
                matched_results.append({
                    'firewall': fw,
                    'firewall_id': fw.id,
                    'direction': direction,
                    'device_source_zone': fw_src_zone or fallback_internal_zone,
                    'device_dest_zone': fw_dst_zone or fallback_external_zone,
                    'match_method': 'ip_asset_match'
                })

        return matched_results

    # ============================================================
    #                      内部工具层 (新设计)
    # ============================================================

    def _find_zone_by_ip(
        self, ip_obj: Optional[ipaddress.IPv4Address], fw: Firewall
    ) -> Tuple[Optional[str], Optional[FirewallZone]]:
        """返回 (zone_name, zone_object) — IP 命中的 zone"""
        if not ip_obj or not fw.zones:
            return (None, None)
        for zone in fw.zones:
            if zone.protected_ips:
                for ip_range in zone.protected_ips.strip().split('\n'):
                    ip_range = ip_range.strip()
                    if not ip_range:
                        continue
                    try:
                        if ip_obj in ipaddress.ip_network(ip_range, strict=False):
                            return (zone.zone_name, zone)
                    except Exception:
                        continue
        return (None, None)

    def _is_zone_internal(
        self, zone: Optional[FirewallZone], fw: Firewall
    ) -> bool:
        """判断 zone 是否属于防火墙的 internal 侧

        判定优先级 (设计文档 §1):
          1. 显式: zone.zone_role == 'internal' → True; == 'external' → False
          2. 降级 (历史数据 / zone_role 字段未填时): zone.connect_region == firewall.belong_region → internal
        """
        if not zone:
            return False

        # 优先级 1: 显式 zone_role (设计文档 §1 强制)
        if zone.zone_role == "internal":
            return True
        if zone.zone_role == "external":
            return False

        # 优先级 2: 降级到隐式判定 (兼容历史)
        if not zone.connect_region:
            return False
        if not fw.belong_region:
            return False
        return zone.connect_region == fw.belong_region

    def _get_fallback_zone_name(self, fw: Firewall, internal: bool) -> str:
        """防火墙无 FirewallZone 时, 从 ZoneAccessConfig 找兜底 zone 名"""
        from app.models import ZoneAccessConfig
        cfgs = list(fw.zone_access_configs or [])
        if not cfgs:
            cfgs = self.db.query(ZoneAccessConfig).filter_by(firewall_id=fw.id).all()
        if not cfgs:
            return "Trust" if internal else "Untrust"
        cfg = cfgs[0]
        return cfg.boundary_source_zone if internal else cfg.boundary_dest_zone

    def _parse_to_ip_object(self, ip_str: str, field_label: str) -> Optional[ipaddress.IPv4Address]:
        if not ip_str:
            return None
        extracted = self._extract_first_ip(ip_str)
        try:
            if '/' in extracted:
                return ipaddress.ip_network(extracted, strict=False).network_address
            return ipaddress.ip_address(extracted)
        except Exception as e:
            logger.warning(f"[{field_label}] 无法转换文本 '{ip_str}' 为有效IP对象: {e}")
            return None

    def _extract_first_ip(self, ip_str: str) -> str:
        """从多元素/不规范文本中提取第一个合法 IP"""
        if not ip_str:
            return ""
        normalized = ip_str.replace('\r\n', '\n').replace(',', '\n').replace(';', '\n').replace('；', '\n')
        for line in normalized.split('\n'):
            line = line.strip()
            if not line:
                continue
            for part in line.split(','):
                part = part.strip()
                if not part:
                    continue
                if '-' in part and '/' not in part:
                    first = part.split('-')[0].strip()
                    try:
                        ipaddress.ip_address(first)
                        return first
                    except ValueError:
                        continue
                if '/' in part:
                    first = part.split('/')[0].strip()
                    try:
                        ipaddress.ip_address(first)
                        return first
                    except ValueError:
                        continue
                try:
                    ipaddress.ip_address(part)
                    return part
                except ValueError:
                    continue
        return ""

    def _check_ip_in_raw_text_ranges(self, ip_obj: ipaddress.IPv4Address, raw_ranges_text: str) -> bool:
        if not raw_ranges_text:
            return False
        for ip_range in raw_ranges_text.strip().split('\n'):
            ip_range = ip_range.strip()
            if not ip_range:
                continue
            try:
                if ip_obj in ipaddress.ip_network(ip_range, strict=False):
                    return True
            except Exception:
                continue
        return False

    def should_push_same_firewall_policy(self, firewall: Firewall, direction: str) -> Tuple[bool, Optional[str]]:
        """新设计: allow_same_firewall_push 字段已删除, 同墙策略默认允许推送"""
        # 同墙策略不再受字段开关限制, 直接返回允许
        return True, None