"""
NAT转换分析模块（SNAT-only 版本）

项目决定: 取消 DNAT 分析。跨区域访问仅按 SNAT 处理。

判断流程（按用户业务语义）：
  1. 通过 firewall 的 protected_ips 段判断 src/dst 属于 external/internal
  2. 同区域：不需要 NAT
  3. 跨区域：默认需要 SNAT（源 IP 转换）
  4. SNAT 地址池:
       - 源在 internal 侧（出向）→ 用 outbound_snat_pool
       - 源在 external 侧（入向）→ 用 inbound_snat_pool
     任一未配置 → 警告。
  5. 项目已不再分析 DNAT, 故 nat_type 只会是 'SNAT' 或 None;
     None 的场景仅在防火墙 SNAT 池完全未配置时返回, 由人工补配。
"""
from typing import Optional, Dict, List
import ipaddress
from sqlalchemy.orm import Session
from app.models import Firewall


class NATAnalyzer:
    """
    NAT转换分析器（SNAT-only）
    """

    def __init__(self, db: Session):
        self.db = db

    def analyze_policy(self, source_ip: str, dest_ip: str, firewall: Firewall) -> Dict:
        """
        分析策略是否需要 NAT 转换

        返回格式：
        {
            "need_nat": bool,
            "nat_type": "SNAT" | None,
            "snat_address": str | None,
            "dnat_address": None,           # 保留字段以兼容调用方, 永远为 None
            "source_zone": str | None,
            "dest_zone": str | None,
            "warnings": List[str]
        }
        """
        result = {
            "need_nat": False,
            "nat_type": None,
            "snat_address": None,
            "dnat_address": None,           # 项目已取消 DNAT, 保留字段恒为 None
            "source_zone": None,
            "dest_zone": None,
            "source_zone_name": None,       # 业务名: 对应 firewall.local_zone_name / external_zone_name
            "dest_zone_name": None,
            "warnings": []
        }

        # zone 判定(流量方向属性 internal/external): 任何防火墙都做, 跟是否做 NAT 无关
        # 非边界墙不进入 NAT 判定, 但 zone 判定仍执行 → nat_info.source_zone/dest_zone 始终有值
        try:
            source_zone = self._get_zone(source_ip, firewall)
            dest_zone = self._get_zone(dest_ip, firewall)
            result["source_zone"] = source_zone
            result["dest_zone"] = dest_zone
            # 业务名映射: internal → firewall.local_zone_name, external → firewall.external_zone_name
            result["source_zone_name"] = (
                firewall.local_zone_name if source_zone == "internal"
                else firewall.external_zone_name if source_zone == "external"
                else None
            )
            result["dest_zone_name"] = (
                firewall.local_zone_name if dest_zone == "internal"
                else firewall.external_zone_name if dest_zone == "external"
                else None
            )
        except Exception as e:
            result["warnings"].append(f"zone 判定失败: {str(e)}")

        # 非边界墙: 跳过 NAT 判定, 直接返回 (zone 已填好, 前端可显示流量方向)
        if not firewall.is_zone_boundary:
            if not result["source_zone"] or not result["dest_zone"]:
                result["warnings"].append("无法判断IP所属区域")
            return result

        try:
            # 步骤 2: NAT 判定（仅边界墙, zone 判定已在前面的 try 完成）
            if not result["source_zone"] or not result["dest_zone"]:
                result["warnings"].append("无法判断IP所属区域")
                return result

            # 同区域：不需要 NAT
            if result["source_zone"] == result["dest_zone"]:
                return result

            # 跨区域：仅按 SNAT 处理
            result["need_nat"] = True
            result["nat_type"] = "SNAT"

            # 源在 internal 侧 → 出向（outbound_snat_pool）
            # 源在 external 侧 → 入向（inbound_snat_pool）
            if result["source_zone"] == "internal" and result["dest_zone"] == "external":
                result["snat_address"] = firewall.outbound_snat_pool
                if not result["snat_address"]:
                    result["warnings"].append("出向SNAT地址池未配置")
            elif result["source_zone"] == "external" and result["dest_zone"] == "internal":
                result["snat_address"] = firewall.inbound_snat_pool
                if not result["snat_address"]:
                    result["warnings"].append("入向SNAT地址池未配置")
            else:
                # 源或目的不在 internal/external 分类内（理论上 _get_zone 不会返回其他值）
                result["warnings"].append(f"未知区域组合: source={result['source_zone']}, dest={result['dest_zone']}")
                result["snat_address"] = firewall.outbound_snat_pool
                if not result["snat_address"]:
                    result["warnings"].append("出向SNAT地址池未配置")

            return result

        except Exception as e:
            result["warnings"].append(f"NAT分析失败: {str(e)}")
            return result

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
