"""
NAT 转换分析器 (SNAT-only) — 纯物理矩阵双向匹配版

核心修复 (2026-06-27):
  - 彻底剥离宏观大区判断包袱，完全依赖 Zone 物理属性。
  - 引入【源/目双向矩阵碰撞】：只对 ZoneAccessConfig 中明确配置了
    `boundary_source_zone` -> `boundary_dest_zone` 且开启 `need_nat=1` 的流量方向执行 SNAT。
  - 完美解决入向流量（外网访问内网）或未经配置的内网跨域流量被误加 SNAT 的问题。
"""
from typing import Optional, Dict, Tuple
import ipaddress
import logging
from sqlalchemy.orm import Session
from app.models import Firewall, FirewallZone, ZoneAccessConfig

logger = logging.getLogger(__name__)


class NATAnalyzer:
    def __init__(self, db: Session):
        self.db = db

    def analyze_policy_with_context(
        self, policy_src_ip: str, policy_dst_ip: str, firewall: Firewall, match_context: Optional[Dict] = None
    ) -> Dict:
        result = {
            "need_nat": False,
            "nat_type": None,
            "snat_address": None,
            "dnat_address": None,
            "source_zone": None,
            "dest_zone": None,
            "source_zone_name": None,
            "dest_zone_name": None,
            "warnings": []
        }

        try:
            # 1. 物理安全域快速检索
            if match_context and match_context.get('firewall_id') == firewall.id:
                src_device_zone = match_context.get('device_source_zone')
                dst_device_zone = match_context.get('device_dest_zone')
            else:
                src_ip_obj = self._parse_to_ip_object(policy_src_ip)
                dst_ip_obj = self._parse_to_ip_object(policy_dst_ip)
                src_device_zone = self._find_device_zone_name_by_ip(src_ip_obj, firewall)
                dst_device_zone = self._find_device_zone_name_by_ip(dst_ip_obj, firewall)

            result["source_zone_name"] = src_device_zone
            result["dest_zone_name"] = dst_device_zone

            # 3. 剥离大区，仅依赖 explicit role
            result["source_zone"] = self._classify_zone_side(src_device_zone, firewall)
            result["dest_zone"] = self._classify_zone_side(dst_device_zone, firewall)

        except Exception as e:
            result["warnings"].append(f"安全域资产特征提取异常: {str(e)}")
            return result

        # 如果不是边界墙，直接跳过 NAT 判定
        if not firewall.is_zone_boundary:
            if result["source_zone"] == "unknown" or result["dest_zone"] == "unknown":
                result["warnings"].append(f"防火墙 [{firewall.name}] 无法通过防护资产精准定位源或目的 IP 的安全域侧向归属")
            return result

        # 4. 边界墙 NAT 双向矩阵精准碰撞
        try:
            if src_device_zone == dst_device_zone and src_device_zone is not None:
                return result

            # 💡 核心修复：把源和目的物理名称都传进去，严查矩阵方向
            snat_pool, fallback_warning, is_path_configured = self._resolve_snat_pool(
                firewall, result["source_zone_name"], result["dest_zone_name"]
            )

            # 如果矩阵里压根没配置这条方向的线（比如外网进内网 Untrust -> Trust），说明无需 SNAT，直接放行
            if not is_path_configured:
                return result

            # 走到这里，说明是配置了且必须走 SNAT 的方向（如 Trust -> Untrust）
            result["need_nat"] = True
            result["nat_type"] = "SNAT"
            result["snat_address"] = snat_pool

            if not snat_pool:
                if fallback_warning:
                    result["warnings"].append(fallback_warning)
                else:
                    result["warnings"].append(
                        f"防火墙 [{firewall.name}] 跨域路径 {result['source_zone_name']} -> {result['dest_zone_name']} SNAT 地址池未配置"
                    )

            if result["need_nat"] and not result["snat_address"]:
                result["nat_type"] = None  # 地址池为空则挂起

            return result

        except Exception as e:
            result["warnings"].append(f"边界墙 NAT 矩阵深度推导失败: {str(e)}")
            return result


    # ============================================================
    #                      内部检索工具
    # ============================================================

    def _find_device_zone_name_by_ip(
        self, ip_obj: Optional[ipaddress.IPv4Address], fw: Firewall
    ) -> Optional[str]:
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

    def _get_fallback_zone_name(self, fw: Firewall, internal: bool) -> str:
        cfgs = list(fw.zone_access_configs or [])
        if not cfgs:
            cfgs = self.db.query(ZoneAccessConfig).filter_by(firewall_id=fw.id).all()
        if not cfgs:
            return "Trust" if internal else "Untrust"
        cfg = cfgs[0]
        return cfg.boundary_source_zone if internal else cfg.boundary_dest_zone

    def _classify_zone_side(self, device_zone_name: Optional[str], fw: Firewall) -> str:
        if not device_zone_name:
            return "unknown"
        zone = None
        for z in (fw.zones or []):
            if z.zone_name == device_zone_name:
                zone = z
                break
        if not zone:
            return "unknown"
        if zone.zone_role in ("internal", "external"):
            return zone.zone_role
        return "unknown"

    def _resolve_snat_pool(
        self, fw: Firewall, src_zone: Optional[str], dst_zone: Optional[str]
    ) -> Tuple[Optional[str], Optional[str], bool]:
        """
        核心修复: 基于源和目的的物理 Zone 名字，去撞击 ZoneAccessConfig 矩阵。
        返回: (snat_pool, 警告提示, 是否在矩阵中匹配到该路径)
        """
        cfgs = list(fw.zone_access_configs or [])
        if not cfgs:
            cfgs = self.db.query(ZoneAccessConfig).filter_by(firewall_id=fw.id).all()
        if not cfgs:
            return None, "防火墙无边界路由转换配置", False

        matched_cfg = None
        if src_zone and dst_zone:
            for cfg in cfgs:
                # 双向严格匹配
                if cfg.boundary_source_zone == src_zone and cfg.boundary_dest_zone == dst_zone:
                    matched_cfg = cfg
                    break

        if not matched_cfg:
            # 路径没在配置表里（比如入向 Untrust -> Trust），这是合法现象，代表“该方向不转 NAT”
            return None, None, False

        if not matched_cfg.need_nat:
            # 路径在表里，但管理员手动关闭了该路径的 NAT (need_nat=0)
            return None, f"跨域路径 {src_zone} -> {dst_zone} 匹配，但转换策略未启用 (need_nat=0)", True

        return matched_cfg.snat_pool, None, True

    def _parse_to_ip_object(self, ip_str: str) -> Optional[ipaddress.IPv4Address]:
        if not ip_str:
            return None
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