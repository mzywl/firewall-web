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
    """防火墙智能匹配器（纯 IP 资产维增强版）"""

    def __init__(self, db: Session):
        self.db = db

    def match_by_policy_context(self, policy: Policy) -> List[Dict]:
        """
        核心匹配接口：完全基于【源IP、目的IP】精准匹配防火墙
        （已废弃原有的 ZoneAccessConfig 区域矩阵名称匹配）
        """
        logger.info(f"策略ID {policy.id}: 开始通过 [FirewallZone / IP网络资产] 进行归属判定... "
                    f"(Src: {policy.source_ip} -> Dst: {policy.dest_ip})")

        return self._match_by_ip_assets(policy)

    # ============================================================
    #                      IP 资产精准匹配核心
    # ============================================================

    def _match_by_ip_assets(self, policy: Policy) -> List[Dict]:
        """利用 FirewallZone 的网段资产及内外网段配置进行全表扫描匹配"""
        matched_results = []
        src_ip_obj = self._parse_to_ip_object(policy.source_ip, "源IP")
        dst_ip_obj = self._parse_to_ip_object(policy.dest_ip, "目的IP")

        if not src_ip_obj and not dst_ip_obj:
            return []

        # 捞出所有启用的防火墙
        all_firewalls = self.db.query(Firewall).filter(Firewall.is_active == 1).all()

        for fw in all_firewalls:
            # 1. 优先查防火墙具体的细分区域表 (firewall_zones)
            fw_src_zone = self._find_device_zone_name_by_ip(src_ip_obj, fw)
            fw_dst_zone = self._find_device_zone_name_by_ip(dst_ip_obj, fw)

            source_in_internal = bool(fw_src_zone and fw_src_zone == fw.local_zone_name)
            dest_in_internal = bool(fw_dst_zone and fw_dst_zone == fw.local_zone_name)

            # 2. 如果细分区域没查到，用原来旧资产表的模糊大网段兜底判定
            if not fw_src_zone and src_ip_obj:
                source_in_internal = self._check_ip_in_raw_text_ranges(src_ip_obj, fw.internal_protected_ips)
                source_in_external = self._check_ip_in_raw_text_ranges(src_ip_obj, fw.external_protected_ips)
                if source_in_internal:
                    fw_src_zone = fw.local_zone_name
                elif source_in_external:
                    fw_src_zone = fw.external_zone_name

            if not fw_dst_zone and dst_ip_obj:
                dest_in_internal = self._check_ip_in_raw_text_ranges(dst_ip_obj, fw.internal_protected_ips)
                dest_in_external = self._check_ip_in_raw_text_ranges(dst_ip_obj, fw.external_protected_ips)
                if dest_in_internal:
                    fw_dst_zone = fw.local_zone_name
                elif dest_in_external:
                    fw_dst_zone = fw.external_zone_name

            # 3. 核心方向与归属判定逻辑（纯 IP 增强型拓扑判定）
            # 如果这台防火墙连源 IP 和目的 IP 都不认识，说明流量不经过它
            if not fw_src_zone and not fw_dst_zone:
                continue

            direction = None

            # 情况 A: 源和目的都在该墙资产内被识别
            if fw_src_zone and fw_dst_zone:
                if fw_src_zone == fw_dst_zone and source_in_internal:
                    direction = 'same_firewall'
                elif source_in_internal and not dest_in_internal:
                    direction = 'outbound'
                elif not source_in_internal and dest_in_internal:
                    direction = 'inbound'
                else:
                    direction = 'outbound'  # 跨外部区域默认出向

            # 情况 B: 只有源 IP 属于该墙内网，目的 IP 是外部未知网段 (常规出向流量)
            elif source_in_internal:
                direction = 'outbound'
                fw_dst_zone = fw.external_zone_name or "Untrust"

            # 情况 C: 只有目的 IP 属于该墙内网，源 IP 是外部未知网段 (常规入向流量)
            elif dest_in_internal:
                direction = 'inbound'
                fw_src_zone = fw.external_zone_name or "Untrust"

            else:
                # 识别出的 IP 都在外网，未知内网归属，安全起见略过这台墙
                continue

            if direction:
                matched_results.append({
                    'firewall': fw,
                    'firewall_id': fw.id,
                    'direction': direction,
                    'device_source_zone': fw_src_zone or fw.local_zone_name or "Trust",
                    'device_dest_zone': fw_dst_zone or fw.external_zone_name or "Untrust",
                    'match_method': 'ip_asset_match'
                })

        return matched_results

    # ============================================================
    #                      内部工具层（保持高效不变）
    # ============================================================

    def _find_device_zone_name_by_ip(self, ip_obj: Optional[ipaddress.IPv4Address], fw: Firewall) -> Optional[str]:
        """辅助方法：去 firewall_zones 细分区域资产里，看这个 IP 究竟落在哪个区域网段里"""
        if not ip_obj or not fw.zones:
            return None

        for zone in fw.zones:
            if zone.protected_ips:
                for ip_range in zone.protected_ips.strip().split('\n'):
                    ip_range = ip_range.strip()
                    if not ip_range:
                        continue
                    try:
                        if ip_obj in ipaddress.ip_network(ip_range, strict=False):
                            return zone.zone_name
                    except Exception:
                        continue
        return None

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
        if direction == 'same_firewall':
            if getattr(firewall, 'allow_same_firewall_push', False):
                return True, None
            else:
                return False, NOT_PUSHED_REASONS['SAME_FIREWALL_NOT_ALLOWED']
        return True, None