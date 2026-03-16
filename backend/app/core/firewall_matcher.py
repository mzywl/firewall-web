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
        
        匹配规则（必须源或目的至少有一个在内部区域）：
        1. 源IP在内部 + 目的IP在内部 → 同墙
        2. 源IP在内部 + 目的IP在外部 → 出向
        3. 源IP在外部 + 目的IP在内部 → 入向
        4. 其他情况 → 未匹配
        
        返回: [
            {
                'firewall': Firewall对象,
                'direction': 'outbound' | 'inbound' | 'same_firewall',
                'source_in_internal': bool,
                'source_in_external': bool,
                'dest_in_internal': bool,
                'dest_in_external': bool
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
                source_in_internal = False
                source_in_external = False
                dest_in_internal = False
                dest_in_external = False
                
                # 检查源IP
                if source_ip_obj:
                    source_in_internal = self._ip_in_internal_range(source_ip_obj, firewall)
                    if not source_in_internal:
                        source_in_external = self._ip_in_external_range(source_ip_obj, firewall)
                
                # 检查目的IP
                if dest_ip_obj:
                    dest_in_internal = self._ip_in_internal_range(dest_ip_obj, firewall)
                    if not dest_in_internal:
                        dest_in_external = self._ip_in_external_range(dest_ip_obj, firewall)
                
                # 判断流量方向（必须源或目的至少有一个在内部）
                direction = None
                
                if source_in_internal:
                    # 源IP在内部
                    if dest_in_internal:
                        direction = 'same_firewall'  # 同墙
                    elif dest_in_external:
                        direction = 'outbound'  # 出向
                    # 如果目的IP既不在内部也不在外部，direction保持None（未匹配）
                elif source_in_external:
                    # 源IP在外部
                    if dest_in_internal:
                        direction = 'inbound'  # 入向
                    # 其他情况direction保持None（未匹配）
                # 如果源IP既不在内部也不在外部，direction保持None（未匹配）
                
                # 只有明确匹配到方向的才加入结果
                if direction:
                    matched_firewalls.append({
                        'firewall': firewall,
                        'direction': direction,
                        'source_in_internal': source_in_internal,
                        'source_in_external': source_in_external,
                        'dest_in_internal': dest_in_internal,
                        'dest_in_external': dest_in_external
                    })
            
            return matched_firewalls
        except Exception as e:
            print(f"防火墙匹配失败: {str(e)}")
            return []
    
    def should_push_same_firewall_policy(self, firewall: Firewall, direction: str) -> tuple:
        """
        判断策略是否应该推送
        
        参数:
            firewall: 防火墙对象
            direction: 流量方向 ('outbound' | 'inbound' | 'same_firewall')
        
        返回: (should_push: bool, reason: Optional[str])
        """
        # 同墙策略需要检查配置
        if direction == 'same_firewall':
            # 检查防火墙配置的"同墙推送"选项
            if firewall.allow_same_firewall_push:
                return True, None  # 推送，无原因
            else:
                return False, NOT_PUSHED_REASONS['SAME_FIREWALL_NOT_ALLOWED']
        
        # 出向和入向策略正常推送
        return True, None
    
    def _extract_first_ip(self, ip_str: str) -> str:
        """
        提取第一个IP地址
        支持格式：
        - 单个IP: 10.2.179.127
        - 逗号分隔: 10.2.179.127,10.2.179.128
        - IP范围: 10.2.179.127-10.2.179.132
        - 换行分隔: 10.2.179.127\n10.2.179.128
        """
        if not ip_str:
            return ""
        
        # 先按换行分割
        lines = ip_str.strip().split('\n')
        first_line = lines[0].strip() if lines else ip_str.strip()
        
        # 再按逗号分割
        parts = first_line.split(',')
        first_part = parts[0].strip() if parts else first_line
        
        # 处理IP范围（如 10.2.179.127-10.2.179.132）
        if '-' in first_part:
            range_parts = first_part.split('-')
            if range_parts:
                return range_parts[0].strip()
        
        return first_part
    
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
    
    def _ip_in_external_range(self, ip_obj: ipaddress.IPv4Address, firewall: Firewall) -> bool:
        """
        检查 IP 是否在防火墙外部防护IP段内
        """
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
