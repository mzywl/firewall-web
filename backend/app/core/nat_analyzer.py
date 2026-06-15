"""
NAT转换分析模块

判断流程（按用户业务语义）：
  1. 通过 firewall 的 protected_ips 段判断 src/dst 属于 external/internal
  2. firewall 上是否勾了 NAT 池（任一非空）
  3. 查 zone_access_configs 表，按 firewall 自身的 zone 名匹配
  4. 命中且 nat_type 非空 → 直接用配置
     命中但 nat_type 为空 → 提示并 fallback
     未命中 → fallback 到 IP 段判定（外部→内部=DNAT, 内部→外部=SNAT）
"""
from typing import Optional, Dict, List
import ipaddress
from sqlalchemy.orm import Session
from app.models import Firewall, ZoneAccessConfig


class NATAnalyzer:
    """
    NAT转换分析器
    """

    def __init__(self, db: Session):
        self.db = db

    def analyze_policy(self, source_ip: str, dest_ip: str, firewall: Firewall) -> Dict:
        """
        分析策略是否需要NAT转换

        返回格式：
        {
            "need_nat": bool,
            "nat_type": "SNAT" | "DNAT" | "BOTH" | None,
            "snat_address": str | None,
            "dnat_address": str | None,
            "source_zone": str | None,
            "dest_zone": str | None,
            "warnings": List[str]
        }
        """
        result = {
            "need_nat": False,
            "nat_type": None,
            "snat_address": None,
            "dnat_address": None,
            "source_zone": None,
            "dest_zone": None,
            "warnings": []
        }

        try:
            # 步骤 1: 通过 firewall 的 protected_ips 段判断 src/dst 所属网络 zone
            source_zone = self._get_zone(source_ip, firewall)
            dest_zone = self._get_zone(dest_ip, firewall)

            result["source_zone"] = source_zone
            result["dest_zone"] = dest_zone

            # 无法判断区域（如 IP 不在任何 protected_ips 段）
            if not source_zone or not dest_zone:
                result["warnings"].append("无法判断IP所属区域")
                return result

            # 同区域：不需要 NAT
            if source_zone == dest_zone:
                return result

            # 跨区域：需要 NAT
            result["need_nat"] = True

            # 步骤 3: 查 zone_access_configs 表（业务视角优先）
            # 用 firewall 自身的 zone 名（external_zone_name + region）
            # 去匹配 configs.source_zone / configs.dest_zone
            # 注意：zone_access_configs 表本身就是"业务上明确指定 NAT 类型"的强信号，
            #       只要表中配了该 firewall + (source_zone, dest_zone) → 立即用配置，
            #       不被 firewall 是否配 NAT 池字段 gate（NAT 池字段决定具体地址，
            #       但不影响 NAT 类型判定）。
            # 注：local_zone_name 是"内网 zone 名"（业务名，可被改），不是"归属大区"；
            #     region 才是 firewall 归属的大区（用于查表更稳定）。
            ext_zone = firewall.external_zone_name
            local_zone = firewall.region  # 归属大区

            if source_zone == "external" and dest_zone == "internal":
                cfg = self.db.query(ZoneAccessConfig).filter(
                    ZoneAccessConfig.firewall_id == firewall.id,
                    ZoneAccessConfig.source_zone == ext_zone,
                    ZoneAccessConfig.dest_zone == local_zone,
                ).first()
            elif source_zone == "internal" and dest_zone == "external":
                cfg = self.db.query(ZoneAccessConfig).filter(
                    ZoneAccessConfig.firewall_id == firewall.id,
                    ZoneAccessConfig.source_zone == local_zone,
                    ZoneAccessConfig.dest_zone == ext_zone,
                ).first()
            else:
                cfg = None

            if cfg and cfg.nat_type:
                # 步骤 4: 命中且配了 nat_type → 直接用配置
                return self._build_nat_result(result, cfg.nat_type, firewall)

            if cfg is not None:
                # 配了记录但没指定 nat_type → 提示后 fallback
                result["warnings"].append(
                    f"区域访问配置已配(source={cfg.source_zone}, dest={cfg.dest_zone})但未指定 nat_type, fallback 到默认判定"
                )

            # 步骤 5: fallback — 按网络方向默认判定
            return self._fallback_by_network_direction(result, firewall)

        except Exception as e:
            result["warnings"].append(f"NAT分析失败: {str(e)}")
            return result

    def _build_nat_result(self, result: Dict, nat_type: str, firewall: Firewall) -> Dict:
        """根据配置/默认的 nat_type 填充结果（地址池/警告）"""
        result["nat_type"] = nat_type

        if nat_type == "SNAT":
            # 源 IP 转换：源在 internal 侧，源 IP 转成 outbound_snat_pool
            result["snat_address"] = firewall.outbound_snat_pool
            if not result["snat_address"]:
                result["warnings"].append("出向SNAT地址池未配置")
        elif nat_type == "DNAT":
            # 目的 IP 转换：目的在 internal 侧，目的 IP 转成 inbound_dnat_pool
            result["dnat_address"] = firewall.inbound_dnat_pool
            if not result["dnat_address"]:
                result["warnings"].append("入向DNAT地址池未配置")
        elif nat_type == "BOTH":
            result["snat_address"] = firewall.outbound_snat_pool
            result["dnat_address"] = firewall.inbound_dnat_pool
            if not result["snat_address"]:
                result["warnings"].append("SNAT地址池未配置")
            if not result["dnat_address"]:
                result["warnings"].append("DNAT地址池未配置")

        return result

    def _fallback_by_network_direction(self, result: Dict, firewall: Firewall) -> Dict:
        """Fallback: 按网络方向判定 NAT 类型（外部→内部=DNAT, 内部→外部=SNAT）"""
        if result["source_zone"] == "internal" and result["dest_zone"] == "external":
            return self._build_nat_result(result, "SNAT", firewall)
        elif result["source_zone"] == "external" and result["dest_zone"] == "internal":
            return self._build_nat_result(result, "DNAT", firewall)
        else:
            return self._build_nat_result(result, "BOTH", firewall)

    def _get_zone(self, ip: str, firewall: Firewall) -> Optional[str]:
        """
        判断IP属于哪个区域
        返回: "internal" | "external" | None
        """
        if not ip:
            return None

        try:
            # 提取第一个IP地址
            ip_str = self._extract_first_ip(ip)
            if not ip_str:
                return None

            ip_obj = ipaddress.ip_address(ip_str)

            # 检查是否在内部防护IP段
            if firewall.internal_protected_ips:
                for ip_range in firewall.internal_protected_ips.strip().split('\n'):
                    ip_range = ip_range.strip()
                    if not ip_range:
                        continue
                    try:
                        network = ipaddress.ip_network(ip_range, strict=False)
                        if ip_obj in network:
                            return "internal"
                    except Exception:
                        continue

            # 检查是否在外部防护IP段
            if firewall.external_protected_ips:
                for ip_range in firewall.external_protected_ips.strip().split('\n'):
                    ip_range = ip_range.strip()
                    if not ip_range:
                        continue
                    try:
                        network = ipaddress.ip_network(ip_range, strict=False)
                        if ip_obj in network:
                            return "external"
                    except Exception:
                        continue

            return None

        except Exception:
            return None

    def _extract_first_ip(self, ip_str: str) -> Optional[str]:
        """提取第一个IP地址"""
        if not ip_str:
            return None

        # 处理多个IP的情况（逗号、分号、空格分隔）
        for sep in [',', ';', ' ', '\n']:
            if sep in ip_str:
                parts = ip_str.split(sep)
                for part in parts:
                    part = part.strip()
                    if part and '.' in part:
                        # 移除CIDR后缀
                        if '/' in part:
                            part = part.split('/')[0]
                        return part

        # 单个IP
        ip_str = ip_str.strip()
        if '/' in ip_str:
            ip_str = ip_str.split('/')[0]

        return ip_str if '.' in ip_str else None
