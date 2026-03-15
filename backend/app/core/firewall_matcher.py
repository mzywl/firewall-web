"""
防火墙匹配模块
"""
from typing import Optional, List, Dict
import ipaddress
from sqlalchemy.orm import Session
from app.models import Firewall


# 不推送原因枚举
NOT_PUSHED_REASONS = {
    'SAME_FIREWALL_NOT_ALLOWED': '源目的IP均在同一防火墙内部，未启用同墙推送',
    'NO_FIREWALL_MATCH': '未匹配到任何防火墙',
    'NAT_CONFIG_MISSING': 'NAT配置缺失',
    'CROSS_ZONE_NO_NAT': '跨区域策略但无NAT规则'
}


class FirewallMatcher:
    """防火墙匹配器"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def match_by_ip(self, ip: str) -> Optional[int]:
        """
        根据 IP 地址匹配防火墙（单个匹配，保持向后兼容）
        返回: firewall_id 或 None
        """
        matches = self.match_firewalls_by_policy(ip, ip)
        if matches:
            return matches[0]['firewall'].id
        return None
    
    def match_firewalls_by_policy(self, source_ip: str, dest_ip: str) -> List[Dict]:
        """
        根据策略的源IP和目的IP匹配所有相关防火墙
        
        返回: [
            {
                'firewall': Firewall对象,
                'source_match': bool,  # 源IP是否匹配
                'dest_match': bool     # 目的IP是否匹配
            }
        ]
        """
        matched_firewalls = []
        
        try:
            # 解析IP地址
            source_ip_obj = None
            dest_ip_obj = None
            
            if source_ip:
                try:
                    source_ip_obj = ipaddress.ip_address(self._extract_first_ip(source_ip))
                except:
                    pass
            
            if dest_ip:
                try:
                    dest_ip_obj = ipaddress.ip_address(self._extract_first_ip(dest_ip))
                except:
                    pass
            
            # 查询所有启用的防火墙
            firewalls = self.db.query(Firewall).filter(
                Firewall.is_active == 1
            ).all()
            
            for firewall in firewalls:
                source_match = False
                dest_match = False
                
                # 检查源IP是否在内部防护IP段
                if source_ip_obj:
                    source_match = self._ip_in_internal_range(source_ip_obj, firewall)
                
                # 检查目的IP是否在内部防护IP段
                if dest_ip_obj:
                    dest_match = self._ip_in_internal_range(dest_ip_obj, firewall)
                
                # 只要源或目的有一个匹配，就加入结果
                if source_match or dest_match:
                    matched_firewalls.append({
                        'firewall': firewall,
                        'source_match': source_match,
                        'dest_match': dest_match
                    })
            
            return matched_firewalls
        except Exception as e:
            print(f"防火墙匹配失败: {str(e)}")
            return []
    
    def should_push_same_firewall_policy(self, firewall: Firewall, source_match: bool, dest_match: bool) -> tuple:
        """
        判断同墙策略是否应该推送
        
        返回: (should_push: bool, reason: Optional[str])
        """
        # 源和目的都匹配同一防火墙的内部IP段
        if source_match and dest_match:
            # 检查防火墙配置的"同墙推送"选项
            if firewall.allow_same_firewall_push:
                return True, None  # 推送，无原因
            else:
                return False, NOT_PUSHED_REASONS['SAME_FIREWALL_NOT_ALLOWED']
        
        return True, None  # 不是同墙策略，正常推送
    
    def _extract_first_ip(self, ip_str: str) -> str:
        """提取第一个IP地址"""
        if not ip_str:
            return ""
        # 简单处理：取第一个非空部分
        parts = ip_str.strip().split(',')
        if parts:
            return parts[0].strip()
        return ip_str.strip()
    
    def _ip_in_internal_range(self, ip_obj: ipaddress.IPv4Address, firewall: Firewall) -> bool:
        """
        检查 IP 是否在防火墙内部防护IP段内
        """
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
        return False
    
    def _ip_in_range(self, ip_obj: ipaddress.IPv4Address, firewall: Firewall) -> bool:
        """
        检查 IP 是否在防火墙管理范围内（内部或外部）
        """
        # 检查内部防护IP段
        if self._ip_in_internal_range(ip_obj, firewall):
            return True
        
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
