"""
防火墙匹配模块
"""
from typing import Optional, List
import ipaddress
from sqlalchemy.orm import Session
from app.models import Firewall


class FirewallMatcher:
    """防火墙匹配器"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def match_by_ip(self, ip: str) -> Optional[int]:
        """
        根据 IP 地址匹配防火墙
        返回: firewall_id 或 None
        """
        try:
            # 解析 IP 地址
            ip_obj = ipaddress.ip_address(ip)
            
            # 查询所有启用的防火墙
            firewalls = self.db.query(Firewall).filter(
                Firewall.is_active == 1
            ).all()
            
            for firewall in firewalls:
                # 检查防火墙配置中的 IP 段
                if self._ip_in_range(ip_obj, firewall):
                    return firewall.id
            
            return None
        except Exception as e:
            print(f"IP 匹配失败: {str(e)}")
            return None
    
    def _ip_in_range(self, ip_obj: ipaddress.IPv4Address, firewall: Firewall) -> bool:
        """
        检查 IP 是否在防火墙管理范围内
        """
        # 检查内部防护IP段
        if firewall.internal_protected_ips:
            for ip_range in firewall.internal_protected_ips.strip().split('\n'):
                ip_range = ip_range.strip()
                if not ip_range:
                    continue
                try:
                    network = ipaddress.ip_network(ip_range, strict=False)
                    if ip_obj in network:
                        return True
                except Exception:
                    continue
        
        # 检查外部防护IP段
        if firewall.external_protected_ips:
            for ip_range in firewall.external_protected_ips.strip().split('\n'):
                ip_range = ip_range.strip()
                if not ip_range:
                    continue
                try:
                    network = ipaddress.ip_network(ip_range, strict=False)
                    if ip_obj in network:
                        return True
                except Exception:
                    continue
        
        return False
    
    def match_multiple_ips(self, ips: List[str]) -> dict:
        """
        批量匹配多个 IP
        返回: {ip: firewall_id}
        """
        result = {}
        for ip in ips:
            if ip:
                firewall_id = self.match_by_ip(ip)
                result[ip] = firewall_id
        return result
