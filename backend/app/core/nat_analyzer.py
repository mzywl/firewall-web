"""
NAT转换分析模块
"""
from typing import Optional, Dict, List
import ipaddress
from sqlalchemy.orm import Session
from app.models import Firewall


class NATAnalyzer:
    """NAT转换分析器"""
    
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
            # 判断源IP和目的IP所属区域
            source_zone = self._get_zone(source_ip, firewall)
            dest_zone = self._get_zone(dest_ip, firewall)
            
            result["source_zone"] = source_zone
            result["dest_zone"] = dest_zone
            
            # 如果无法判断区域，返回警告
            if not source_zone or not dest_zone:
                result["warnings"].append("无法判断IP所属区域")
                return result
            
            # 判断是否跨区域
            if source_zone == dest_zone:
                # 同区域，不需要NAT
                return result
            
            # 跨区域，需要NAT
            result["need_nat"] = True
            
            # 判断NAT类型和地址
            # 规则：内部→外部 = SNAT（出向），外部→内部 = DNAT（入向）
            if source_zone == "internal" and dest_zone == "external":
                # 出向：需要SNAT
                result["nat_type"] = "SNAT"
                result["snat_address"] = firewall.outbound_snat_pool
                if not result["snat_address"]:
                    result["warnings"].append("出向SNAT地址池未配置")
                    
            elif source_zone == "external" and dest_zone == "internal":
                # 入向：需要DNAT
                result["nat_type"] = "DNAT"
                result["dnat_address"] = firewall.inbound_dnat_pool
                if not result["dnat_address"]:
                    result["warnings"].append("入向DNAT地址池未配置")
            
            else:
                # 其他跨区域情况（如测试区→生产区）
                # 简化处理：双向NAT
                result["nat_type"] = "BOTH"
                result["snat_address"] = firewall.outbound_snat_pool
                result["dnat_address"] = firewall.inbound_dnat_pool
                
                if not result["snat_address"]:
                    result["warnings"].append("SNAT地址池未配置")
                if not result["dnat_address"]:
                    result["warnings"].append("DNAT地址池未配置")
            
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
