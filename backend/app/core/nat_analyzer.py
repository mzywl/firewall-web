"""
NAT转换分析模块（SNAT-only 严格联动版）

项目决定: 取消 DNAT 分析。跨区域访问仅按 SNAT 处理。
"""
from typing import Optional, Dict, List
import ipaddress
import logging
from sqlalchemy.orm import Session
from app.models import Firewall, FirewallZone

logger = logging.getLogger(__name__)


class NATAnalyzer:
    """
    NAT转换分析器（SNAT-only 智能安全联动版）
    """

    def __init__(self, db: Session):
        self.db = db

    def analyze_policy_with_context(self, policy_src_ip: str, policy_dst_ip: str, firewall: Firewall, match_context: Optional[Dict] = None) -> Dict:
        """
        分析策略是否需要 NAT 转换（完美承接严格 IP 匹配器上下文）
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
                # 降级：自主通过严格网段资产去细分区域里查找
                src_ip_obj = self._parse_to_ip_object(policy_src_ip)
                dst_ip_obj = self._parse_to_ip_object(policy_dst_ip)
                src_device_zone = self._find_device_zone_name_by_ip(src_ip_obj, firewall)
                dst_device_zone = self._find_device_zone_name_by_ip(dst_ip_obj, firewall)

            result["source_zone_name"] = src_device_zone or firewall.local_zone_name or "Trust"
            result["dest_zone_name"] = dst_device_zone or firewall.external_zone_name or "Untrust"

            # 💡【核心优化】：改进广义内外网语义映射，消除自定义 Zone 导致的 unknown 陷阱
            # 规则：明确命中 external_zone_name 的归为 external；只要能定位到有效区域且不是 external 的，一律视为 internal（如 DMZ, Prod 均属企业内部隔离域）
            if src_device_zone == firewall.external_zone_name:
                result["source_zone"] = "external"
            elif src_device_zone is not None:
                result["source_zone"] = "internal"
            else:
                result["source_zone"] = "unknown"

            if dst_device_zone == firewall.external_zone_name:
                result["dest_zone"] = "external"
            elif dst_device_zone is not None:
                result["dest_zone"] = "internal"
            else:
                result["dest_zone"] = "unknown"

        except Exception as e:
            result["warnings"].append(f"区域属性判定发生系统异常: {str(e)}")

        # 3. 非边界墙直接跳过 NAT 核心判定
        if not firewall.is_zone_boundary:
            if result["source_zone"] == "unknown" or result["dest_zone"] == "unknown":
                # 由于现在双侧匹配极严，若依然出现 unknown，记录属于真实资产缺失
                result["warnings"].append(f"防火墙 [{firewall.name}] 无法通过防护资产精准定位源或目的IP的安全域归属")
            return result

        # 4. 边界墙核心 SNAT 属性萃取
        try:
            # 如果源物理 Zone 和目的物理 Zone 完全一致，说明在同一个内网隔离区内部，绝不需要边界 SNAT
            if src_device_zone == dst_device_zone and src_device_zone is not None:
                return result

            # 触发跨安全域边界 SNAT 处理流
            result["need_nat"] = True
            result["nat_type"] = "SNAT"

            # 情况 A：源在内网/DMZ，目的在外网 ── 出向 SNAT
            if result["source_zone"] == "internal" and result["dest_zone"] == "external":
                result["snat_address"] = firewall.outbound_snat_pool
                if not result["snat_address"]:
                    result["warnings"].append(f"防火墙 [{firewall.name}] 跨域出向 SNAT 地址池未配置")

            # 情况 B：源在外网，目的在内网/DMZ ── 入向 SNAT
            elif result["source_zone"] == "external" and result["dest_zone"] == "internal":
                result["snat_address"] = firewall.inbound_snat_pool
                if not result["snat_address"]:
                    result["warnings"].append(f"防火墙 [{firewall.name}] 跨域入向 SNAT 地址池未配置")

            else:
                # 拓扑边界模糊时的健壮性兜底
                if result["source_zone"] == "internal" or result["dest_zone"] == "external":
                    result["snat_address"] = firewall.outbound_snat_pool
                    result["warnings"].append("未知的内部跨物理隔离域互访，默认采用出向 SNAT 地址池兜底")
                else:
                    result["snat_address"] = firewall.inbound_snat_pool
                    result["warnings"].append("外部未知网络入向访问，默认采用入向 SNAT 地址池兜底")
            # 如果边界墙触发了 SNAT 但地址池缺失，强制挂起状态，提示人工补配
            if result["need_nat"] and not result["snat_address"]:
                result["nat_type"] = None

            return result

        except Exception as e:
            result["warnings"].append(f"NAT核心矩阵分析失败: {str(e)}")
            return result

    # ============================================================
    #                      内部私有资产检索工具
    # ============================================================

    def _find_device_zone_name_by_ip(self, ip_obj: Optional[ipaddress.IPv4Address], fw: Firewall) -> Optional[str]:
        """去细分区域资产里，看这个 IP 落在哪个具体防火墙物理安全域里"""
        if not ip_obj:
            return None

        # 1. 优先查细分的 FirewallZone
        if fw.zones:
            for zone in fw.zones:
                if zone.protected_ips:
                    for ip_range in zone.protected_ips.strip().split('\n'):
                        ip_range = ip_range.strip()
                        if not ip_range: continue
                        try:
                            if ip_obj in ipaddress.ip_network(ip_range, strict=False):
                                return zone.zone_name
                        except Exception:
                            continue

        # 2. 降级：利用老资产表的内外文本网段字段猜测安全域名称
        if fw.internal_protected_ips:
            if self._check_ip_in_raw_text(ip_obj, fw.internal_protected_ips):
                return fw.local_zone_name or "Trust"
        if fw.external_protected_ips:
            if self._check_ip_in_raw_text(ip_obj, fw.external_protected_ips):
                return fw.external_zone_name or "Untrust"

        return None

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
        【同步升级】：与 FirewallMatcher 保持高强度对齐的 IP 清洗提取器。
        遍历行与标记，自动跳过 FQDN 域名、乱码，支持获取范围 IP 与 CIDR 的起始点。
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
            if not ip_range: continue
            try:
                if ip_obj in ipaddress.ip_network(ip_range, strict=False):
                    return True
            except Exception:
                continue
        return False