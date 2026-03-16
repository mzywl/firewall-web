"""
策略拆分与合并模块
参考旧代码逻辑实现
"""
from typing import List, Dict, Tuple
import ipaddress
from sqlalchemy.orm import Session
from app.models import Firewall


class PolicySplitter:
    """策略拆分器 - 将一行策略拆分成多个防火墙的多条策略"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def split_policy(self, source_ips: List[str], dest_ips: List[str], 
                     service: str, action: str) -> List[Dict]:
        """
        拆分策略：一行可能包含多个源/目的地址，属于不同防火墙
        
        参数:
            source_ips: 源地址列表（已按换行/逗号拆分）
            dest_ips: 目的地址列表
            service: 端口/服务
            action: 动作
        
        返回: [
            {
                'firewall': Firewall对象,
                'source_ips': [匹配到该防火墙的源IP],
                'dest_ips': [匹配到该防火墙的目的IP],
                'service': service,
                'action': action,
                'direction': 'outbound' | 'inbound' | 'same_firewall'
            }
        ]
        """
        result = []
        
        # 查询所有启用的防火墙
        firewalls = self.db.query(Firewall).filter(
            Firewall.is_active == 1
        ).all()
        
        for firewall in firewalls:
            # 匹配源地址
            matched_sources = self._match_ips_to_firewall(source_ips, firewall)
            # 匹配目的地址
            matched_dests = self._match_ips_to_firewall(dest_ips, firewall)
            
            # 判断流量方向
            source_in_internal = any(
                self._ip_in_internal_range(ip, firewall) 
                for ip in matched_sources
            )
            dest_in_internal = any(
                self._ip_in_internal_range(ip, firewall) 
                for ip in matched_dests
            )
            
            # 至少有一个匹配才生成策略
            if matched_sources or matched_dests:
                direction = None
                if source_in_internal and dest_in_internal:
                    direction = 'same_firewall'
                elif source_in_internal:
                    direction = 'outbound'
                elif dest_in_internal:
                    direction = 'inbound'
                
                if direction:
                    result.append({
                        'firewall': firewall,
                        'source_ips': matched_sources if matched_sources else source_ips,
                        'dest_ips': matched_dests if matched_dests else dest_ips,
                        'service': service,
                        'action': action,
                        'direction': direction
                    })
        
        return result
    
    def _match_ips_to_firewall(self, ips: List[str], firewall: Firewall) -> List[str]:
        """匹配IP列表到防火墙，返回匹配的IP"""
        matched = []
        for ip in ips:
            if self._ip_matches_firewall(ip, firewall):
                matched.append(ip)
        return matched
    
    def _ip_matches_firewall(self, ip_str: str, firewall: Firewall) -> bool:
        """判断单个IP是否匹配防火墙"""
        try:
            # 提取第一个IP（处理范围、掩码等）
            ip = self._extract_first_ip(ip_str)
            ip_obj = ipaddress.ip_address(ip)
            
            # 检查内部网段
            if self._ip_in_internal_range(ip_obj, firewall):
                return True
            
            # 检查外部网段
            if self._ip_in_external_range(ip_obj, firewall):
                return True
            
            return False
        except:
            return False
    
    def _extract_first_ip(self, ip_str: str) -> str:
        """提取第一个IP地址"""
        if not ip_str:
            return ""
        
        # 处理IP范围（如 10.2.179.127-10.2.179.132）
        if '-' in ip_str:
            return ip_str.split('-')[0].strip()
        
        # 处理掩码（如 10.0.0.0/8）
        if '/' in ip_str:
            return ip_str.split('/')[0].strip()
        
        return ip_str.strip()
    
    def _ip_in_internal_range(self, ip_obj: ipaddress.IPv4Address, firewall: Firewall) -> bool:
        """检查IP是否在防火墙内部防护IP段内"""
        if firewall.internal_protected_ips:
            for ip_range in firewall.internal_protected_ips.strip().split('\n'):
                ip_range = ip_range.strip()
                if not ip_range:
                    continue
                try:
                    network = ipaddress.ip_network(ip_range, strict=False)
                    if ip_obj in network:
                        return True
                except:
                    continue
        return False
    
    def _ip_in_external_range(self, ip_obj: ipaddress.IPv4Address, firewall: Firewall) -> bool:
        """检查IP是否在防火墙外部防护IP段内"""
        if firewall.external_protected_ips:
            for ip_range in firewall.external_protected_ips.strip().split('\n'):
                ip_range = ip_range.strip()
                if not ip_range:
                    continue
                try:
                    network = ipaddress.ip_network(ip_range, strict=False)
                    if ip_obj in network:
                        return True
                except:
                    continue
        return False


class PolicyMerger:
    """策略合并器 - 合并相同防火墙的策略"""
    
    @staticmethod
    def merge_policies(policies: List[Dict]) -> List[Dict]:
        """
        三步合并：
        1. 合并端口（相同源+目的 → 合并端口）
        2. 合并目的地址（相同源+端口 → 合并目的）
        3. 合并源地址（相同目的+端口 → 合并源）
        """
        # 第一步：合并端口
        policies = PolicyMerger._merge_by_service(policies)
        
        # 第二步：合并目的地址
        policies = PolicyMerger._merge_by_dest(policies)
        
        # 第三步：合并源地址
        policies = PolicyMerger._merge_by_source(policies)
        
        return policies
    
    @staticmethod
    def _merge_by_service(policies: List[Dict]) -> List[Dict]:
        """合并端口：相同源+目的 → 合并端口"""
        merged = []
        used = set()
        
        for i, p1 in enumerate(policies):
            if i in used:
                continue
            
            source_key = '\n'.join(sorted(p1['source_ips']))
            dest_key = '\n'.join(sorted(p1['dest_ips']))
            services = [p1['service']]
            
            for j, p2 in enumerate(policies[i+1:], start=i+1):
                if j in used:
                    continue
                
                source_key2 = '\n'.join(sorted(p2['source_ips']))
                dest_key2 = '\n'.join(sorted(p2['dest_ips']))
                
                if source_key == source_key2 and dest_key == dest_key2:
                    services.append(p2['service'])
                    used.add(j)
            
            merged_policy = p1.copy()
            merged_policy['service'] = '\n'.join(services)
            merged.append(merged_policy)
            used.add(i)
        
        return merged
    
    @staticmethod
    def _merge_by_dest(policies: List[Dict]) -> List[Dict]:
        """合并目的地址：相同源+端口 → 合并目的"""
        merged = []
        used = set()
        
        for i, p1 in enumerate(policies):
            if i in used:
                continue
            
            source_key = '\n'.join(sorted(p1['source_ips']))
            service_key = p1['service']
            dest_ips = p1['dest_ips'].copy()
            
            for j, p2 in enumerate(policies[i+1:], start=i+1):
                if j in used:
                    continue
                
                source_key2 = '\n'.join(sorted(p2['source_ips']))
                service_key2 = p2['service']
                
                if source_key == source_key2 and service_key == service_key2:
                    dest_ips.extend(p2['dest_ips'])
                    used.add(j)
            
            merged_policy = p1.copy()
            merged_policy['dest_ips'] = list(set(dest_ips))
            merged.append(merged_policy)
            used.add(i)
        
        return merged
    
    @staticmethod
    def _merge_by_source(policies: List[Dict]) -> List[Dict]:
        """合并源地址：相同目的+端口 → 合并源"""
        merged = []
        used = set()
        
        for i, p1 in enumerate(policies):
            if i in used:
                continue
            
            dest_key = '\n'.join(sorted(p1['dest_ips']))
            service_key = p1['service']
            source_ips = p1['source_ips'].copy()
            
            for j, p2 in enumerate(policies[i+1:], start=i+1):
                if j in used:
                    continue
                
                dest_key2 = '\n'.join(sorted(p2['dest_ips']))
                service_key2 = p2['service']
                
                if dest_key == dest_key2 and service_key == service_key2:
                    source_ips.extend(p2['source_ips'])
                    used.add(j)
            
            merged_policy = p1.copy()
            merged_policy['source_ips'] = list(set(source_ips))
            merged.append(merged_policy)
            used.add(i)
        
        return merged
