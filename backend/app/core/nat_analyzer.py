"""
NAT 转换分析模块 (SNAT-only) — 对齐 重构.md §1 新设计

项目决定: 取消 DNAT 分析。跨区域访问仅按 SNAT 处理。

新设计 (2026-06-22):
  - Firewall 不再持有 outbound_snat_pool / inbound_snat_pool / internal_protected_ips /
    external_protected_ips / local_zone_name / external_zone_name
  - SNAT 池迁到 ZoneAccessConfig.snat_pool
  - 方向判定改用 FirewallZone.connect_region 跟 ZoneAccessConfig.source_region / dest_region 对比
  - 防火墙物理 zone 名来自 FirewallZone.zone_name
"""
from typing import Optional, Dict, List
import ipaddress
import logging
from sqlalchemy.orm import Session
from app.models import Firewall, FirewallZone, ZoneAccessConfig

logger = logging.getLogger(__name__)


class NATAnalyzer:
    """
    NAT 转换分析器 (SNAT-only)

    新设计核心:
      - src IP 的物理 zone 通过 FirewallZone.protected_ips 匹配得到 zone_name
      - 该 zone 的 connect_region 跟 firewall 的 ZoneAccessConfig.source_region / dest_region
        对比, 决定 source_zone = "internal" / "external"
      - SNAT 池取 cfg.snat_pool (cfg.need_nat=1 才用)
    """

    def __init__(self, db: Session):
        self.db = db

    def analyze_policy_with_context(
        self, policy_src_ip: str, policy_dst_ip: str, firewall: Firewall, match_context: Optional[Dict] = None
    ) -> Dict:
        """
        分析策略是否需要 NAT 转换 (完美承接严格 IP 匹配器上下文)
        """
        result = {
            "need_nat": False,
            "nat_type": None,
            "snat_address": None,
            "dnat_address": None,           # 恒为 None
            "source_zone": None,            # "internal" | "external" | "unknown"
            "dest_zone": None,
            "source_zone_name": None,       # 实际物理区域名 (如 DMZ, Trust)
            "dest_zone_name": None,
            "warnings": []
        }

        # 1. 区域及安全域物理名称锁定
        try:
            if match_context and match_context.get('firewall_id') == firewall.id:
                src_device_zone = match_context.get('device_source_zone')
                dst_device_zone = match_context.get('device_dest_zone')
            else:
                # 降级: 自主通过 FirewallZone 找 IP 归属 zone
                src_ip_obj = self._parse_to_ip_object(policy_src_ip)
                dst_ip_obj = self._parse_to_ip_object(policy_dst_ip)
                src_device_zone = self._find_device_zone_name_by_ip(src_ip_obj, firewall)
                dst_device_zone = self._find_device_zone_name_by_ip(dst_ip_obj, firewall)

            # 取防火墙 zone 名 fallback (新设计: firewall.zones 第一条作为 fallback name)
            fallback_src_zone_name = self._get_fallback_zone_name(firewall, internal=True)
            fallback_dst_zone_name = self._get_fallback_zone_name(firewall, internal=False)

            result["source_zone_name"] = src_device_zone or fallback_src_zone_name
            result["dest_zone_name"] = dst_device_zone or fallback_dst_zone_name

            # 用 FirewallZone.connect_region 跟 ZoneAccessConfig.source_region/dest_region 对比,
            # 决定 source_zone = "internal" / "external"
            result["source_zone"] = self._classify_zone_side(
                src_device_zone, firewall, side="source",
            )
            result["dest_zone"] = self._classify_zone_side(
                dst_device_zone, firewall, side="dest",
            )

        except Exception as e:
            result["warnings"].append(f"区域属性判定发生系统异常: {str(e)}")

        # 3. 非边界墙直接跳过 NAT 核心判定
        if not firewall.is_zone_boundary:
            if result["source_zone"] == "unknown" or result["dest_zone"] == "unknown":
                # 由于现在双侧匹配极严, 若依然出现 unknown, 记录属于真实资产缺失
                result["warnings"].append(f"防火墙 [{firewall.name}] 无法通过防护资产精准定位源或目的IP的安全域归属")
            return result

        # 4. 边界墙核心 SNAT 属性萃取
        try:
            # 如果源物理 Zone 和目的物理 Zone 完全一致, 说明在同一个内网隔离区内部, 绝不需要边界 SNAT
            if src_device_zone == dst_device_zone and src_device_zone is not None:
                return result

            # 触发跨安全域边界 SNAT 处理流
            result["need_nat"] = True
            result["nat_type"] = "SNAT"

            # 找匹配的 cfg (按 direction / zone 匹配)
            snat_pool, fallback_warning = self._resolve_snat_pool(
                firewall, src_device_zone, result["source_zone"], result["dest_zone"],
            )
            result["snat_address"] = snat_pool
            if not snat_pool:
                if fallback_warning:
                    result["warnings"].append(fallback_warning)
                else:
                    direction = "出向" if result["source_zone"] == "internal" else "入向"
                    result["warnings"].append(f"防火墙 [{firewall.name}] 跨域{direction} SNAT 地址池未配置")

            # 如果边界墙触发了 SNAT 但地址池缺失, 强制挂起状态, 提示人工补配
            if result["need_nat"] and not result["snat_address"]:
                result["nat_type"] = None

            return result

        except Exception as e:
            result["warnings"].append(f"NAT核心矩阵分析失败: {str(e)}")
            return result

    # ============================================================
    #                      内部私有资产检索工具
    # ============================================================

    def _find_device_zone_name_by_ip(
        self, ip_obj: Optional[ipaddress.IPv4Address], fw: Firewall
    ) -> Optional[str]:
        """去细分区域资产里, 看这个 IP 落在哪个具体防火墙物理安全域里"""
        if not ip_obj:
            return None

        # 优先查 FirewallZone (新设计主路径)
        if fw.zones:
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

    def _get_fallback_zone_name(self, fw: Firewall, internal: bool) -> str:
        """防火墙没有 FirewallZone 时, 用 ZoneAccessConfig 的 boundary_source/dest_zone 兜底取 zone 名

        internal=True → 取 boundary_source_zone (内网侧 zone)
        internal=False → 取 boundary_dest_zone (外网侧 zone)
        """
        cfgs = list(fw.zone_access_configs or [])
        if not cfgs:
            cfgs = self.db.query(ZoneAccessConfig).filter_by(firewall_id=fw.id).all()
        if not cfgs:
            return "Trust" if internal else "Untrust"
        cfg = cfgs[0]
        return cfg.boundary_source_zone if internal else cfg.boundary_dest_zone

    def _classify_zone_side(
        self, device_zone_name: Optional[str], fw: Firewall, side: str,
    ) -> str:
        """
        把设备 zone 名归类为 "internal" / "external" / "unknown"

        判定逻辑: 在 firewall 的 ZoneAccessConfigs 里找 device_zone_name
          - 如果匹配 cfg.boundary_source_zone (side="source" 时) 或 cfg.boundary_dest_zone
            (side="dest" 时), 且 connect_region 跟 cfg.source_region 一致 → "internal"
          - 否则 → "external"

        简化版: 直接用 FirewallZone.connect_region 跟 cfg.source_region 对比:
          - zone.connect_region == cfg.source_region → "internal" (源侧)
          - zone.connect_region == cfg.dest_region → "external" (目的侧)
        """
        if not device_zone_name:
            return "unknown"

        # 找 zone 实体
        zone = None
        for z in (fw.zones or []):
            if z.zone_name == device_zone_name:
                zone = z
                break

        if not zone or not zone.connect_region:
            return "unknown"

        # 优先级 1: 显式 zone_role (设计文档 §1 强制)
        if zone.zone_role == "internal":
            return "internal"
        if zone.zone_role == "external":
            return "external"

        # 优先级 2: 降级到隐式判定 (兼容历史)
        # 在 cfg 里找: 这个 connect_region 是 source_region 还是 dest_region
        cfgs = list(fw.zone_access_configs or [])
        if not cfgs:
            cfgs = self.db.query(ZoneAccessConfig).filter_by(firewall_id=fw.id).all()

        for cfg in cfgs:
            if zone.connect_region == cfg.source_region:
                return "internal"
            if zone.connect_region == cfg.dest_region:
                return "external"

        # 没有 cfg 命中 → unknown
        return "unknown"

    def _resolve_snat_pool(
        self,
        fw: Firewall,
        src_device_zone: Optional[str],
        source_zone: str,
        dest_zone: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        按 src zone 找对应的 ZoneAccessConfig, 取 cfg.snat_pool

        Returns: (snat_pool, fallback_warning)
        """
        cfgs = list(fw.zone_access_configs or [])
        if not cfgs:
            cfgs = self.db.query(ZoneAccessConfig).filter_by(firewall_id=fw.id).all()
        if not cfgs:
            return (None, "防火墙无 ZoneAccessConfig 配置, 无法判定 SNAT 池")

        # 找 src 所在 zone 对应的 cfg (boundary_source_zone 匹配 src_device_zone)
        matched_cfg = None
        if src_device_zone:
            for cfg in cfgs:
                if cfg.boundary_source_zone == src_device_zone:
                    matched_cfg = cfg
                    break
        if not matched_cfg and cfgs:
            matched_cfg = cfgs[0]

        if not matched_cfg.need_nat:
            return (None, f"防火墙 SNAT 路径未启用 (need_nat=0)")

        if not matched_cfg.snat_pool:
            return (None, None)

        return (matched_cfg.snat_pool, None)

    def _parse_to_ip_object(self, ip_str: str) -> Optional[ipaddress.IPv4Address]:
        """安全转换业务文本为标准单IP比对元"""
        extracted = self._extract_first_ip(ip_str)
        if not extracted:
            return None
        try:
            if '/' in extracted:
                return ipaddress.ip_network(extracted, strict=False).network_address
            return ipaddress.ip_address(extracted)
        except Exception:
            return None

    def _extract_first_ip(self, ip_str: str) -> str:
        """
        【同步升级】: 与 FirewallMatcher 保持高强度对齐的 IP 清洗提取器。
        遍历行与标记, 自动跳过 FQDN 域名、乱码, 支持获取范围 IP 与 CIDR 的起始点。
        """
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
                # 范围 IP: 10.1.1.1-10.1.1.10 -> 尝试起始 IP
                if '-' in part and '/' not in part:
                    first = part.split('-')[0].strip()
                    try:
                        ipaddress.ip_address(first)
                        return first
                    except ValueError:
                        continue
                # CIDR: 10.1.1.0/24 -> 尝试网络地址
                if '/' in part:
                    first = part.split('/')[0].strip()
                    try:
                        ipaddress.ip_address(first)
                        return first
                    except ValueError:
                        continue
                # 单 IP / 跳过 FQDN 与乱码
                try:
                    ipaddress.ip_address(part)
                    return part
                except ValueError:
                    continue
        return ""

    def _check_ip_in_raw_text(self, ip_obj: ipaddress.IPv4Address, raw_text: str) -> bool:
        for ip_range in raw_text.strip().split('\n'):
            ip_range = ip_range.strip()
            if not ip_range:
                continue
            try:
                if ip_obj in ipaddress.ip_network(ip_range, strict=False):
                    return True
            except Exception:
                continue
        return False