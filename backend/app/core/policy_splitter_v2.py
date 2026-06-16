"""
策略拆分与合并模块 V2 - 完全重写
参考旧代码逻辑，确保每个IP独立处理
"""
from typing import List, Dict, Tuple, Optional
import ipaddress
import re
from sqlalchemy.orm import Session
from app.models import Firewall


class PolicySplitterV2:
    """策略拆分器 V2 - 将一行策略拆分成多个独立的单IP策略"""
    
    def __init__(self, db: Session):
        self.db = db
        # 排序：边界防火墙(is_zone_boundary=1)排前面，确保 region 内 NAT 状态先建立
        self.firewalls = db.query(Firewall).filter(
            Firewall.is_active == 1
        ).order_by(Firewall.is_zone_boundary.desc(), Firewall.id.asc()).all()
    
    def split_policy_to_single_ips(self, source_ips_str: str, dest_ips_str: str, 
                                     service: str, action: str) -> List[Dict]:
        """
        将一行策略拆分成多个单IP策略
        
        返回: [
            {
                'source_ip': '单个源IP',
                'dest_ip': '单个目的IP',
                'service': service,
                'action': action,
                'firewall': Firewall对象 或 None,
                'direction': 'outbound' | 'inbound' | 'same_firewall' | None,
                'not_pushed_reason': str 或 None
            }
        ]
        """
        result = []
        
        # 拆分源IP和目的IP
        source_ips = self._split_ips(source_ips_str)
        dest_ips = self._split_ips(dest_ips_str)
        
        # 笛卡尔积：每个源IP × 每个目的IP = 一条策略
        for src_ip in source_ips:
            for dst_ip in dest_ips:
                # 匹配所有相关防火墙
                matched_firewalls = self._match_all_firewalls(src_ip, dst_ip)
                
                if not matched_firewalls:
                    # 没有匹配到任何防火墙
                    result.append({
                        'source_ip': src_ip,
                        'dest_ip': dst_ip,
                        'service': service,
                        'action': action,
                        'firewall': None,
                        'direction': None,
                        'not_pushed_reason': '未匹配到任何防火墙'
                    })
                else:
                    # 为每个匹配的防火墙生成策略
                    for firewall, direction in matched_firewalls:
                        policy_item = {
                            'source_ip': src_ip,
                            'dest_ip': dst_ip,
                            'service': service,
                            'action': action,
                            'firewall': firewall,
                            'direction': direction,
                            'not_pushed_reason': None
                        }
                        
                        # 判断是否推送
                        if direction == 'same_firewall':
                            # 同墙策略：检查是否允许同墙推送
                            if not firewall.allow_same_firewall_push:
                                policy_item['not_pushed_reason'] = '源目的IP均在同一防火墙内部，未启用同墙推送'
                        elif direction == 'cross_internal':
                            # 跨防火墙内部通信：不推送
                            policy_item['not_pushed_reason'] = f'源IP在{firewall.name}内部，目的IP在其他防火墙内部，跨防火墙内部通信不推送'
                        
                        result.append(policy_item)
        
        return result
    
    def _split_ips(self, ip_str: str) -> List[str]:
        """拆分IP字符串为单个IP列表"""
        if not ip_str:
            return []
        
        ips = []
        # 按换行符拆分
        lines = ip_str.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 按逗号拆分
            parts = line.split(',')
            for part in parts:
                part = part.strip()
                if part:
                    ips.append(part)
        
        return ips
    
    def _match_all_firewalls(self, source_ip: str, dest_ip: str) -> List[Tuple[Firewall, str]]:
        """
        匹配所有相关防火墙
        
        返回: [(Firewall对象, 方向), ...]
        一条策略可能匹配多个防火墙：
        - 源IP在防火墙A内部 → (A, 'outbound')
        - 目的IP在防火墙B内部 → (B, 'inbound')
        - 源和目的都在防火墙C内部 → (C, 'same_firewall')
        
        特殊情况：源在A内部，目的在B内部（A≠B）
        - 如果目的在B的内部网段 → 标记为 'cross_internal'（跨防火墙内部通信，不推送）
        """
        result = []
        source_matches = []  # [(firewall, is_internal)]
        dest_matches = []
        
        for fw in self.firewalls:
            src_internal = self._ip_in_range(source_ip, fw.internal_protected_ips)
            src_external = self._ip_in_range(source_ip, fw.external_protected_ips)
            dst_internal = self._ip_in_range(dest_ip, fw.internal_protected_ips)
            dst_external = self._ip_in_range(dest_ip, fw.external_protected_ips)
            
            if src_internal or src_external:
                source_matches.append((fw, src_internal))
            if dst_internal or dst_external:
                dest_matches.append((fw, dst_internal))
        
        # 检查同墙策略
        same_firewall_found = False
        for src_fw, src_internal in source_matches:
            for dst_fw, dst_internal in dest_matches:
                if src_fw.id == dst_fw.id and src_internal and dst_internal:
                    # 源和目的都在同一个防火墙内部
                    result.append((src_fw, 'same_firewall'))
                    same_firewall_found = True
                    break
            if same_firewall_found:
                break
        
        # 如果是同墙策略，不再生成其他策略
        if same_firewall_found:
            return result
        
        # 检查跨防火墙内部通信
        # 源在A内部，目的在B内部（A≠B）→ 不推送
        # 修复:必须 src_fw 和 dst_fw 在同一 region 才算"跨防火墙内部通信"
        # 否则 src_fw[生产区] 误吞 src IP + dst_fw[测试区] 命中 dst IP 会被误判
        for src_fw, src_internal in source_matches:
            if src_internal:
                for dst_fw, dst_internal in dest_matches:
                    if dst_internal and src_fw.id != dst_fw.id and src_fw.region == dst_fw.region:
                        # 跨防火墙内部通信，标记为特殊方向
                        result.append((src_fw, 'cross_internal'))
                        return result  # 这种情况不生成其他策略
        
        # 源在某个防火墙的内部网段（出向）
        for fw, is_internal in source_matches:
            if is_internal:
                result.append((fw, 'outbound'))
        
        # 目的在某个防火墙的内部网段（入向）
        for fw, is_internal in dest_matches:
            if is_internal:
                result.append((fw, 'inbound'))
        
        return result
    
    def _match_firewall(self, source_ip: str, dest_ip: str) -> Tuple[Optional[Firewall], Optional[str]]:
        """
        匹配防火墙和流量方向
        
        返回: (Firewall对象, 方向)
        方向: 'outbound' | 'inbound' | 'same_firewall' | None
        """
        source_matches = []  # [(firewall, is_internal)]
        dest_matches = []
        
        for fw in self.firewalls:
            src_internal = self._ip_in_range(source_ip, fw.internal_protected_ips)
            src_external = self._ip_in_range(source_ip, fw.external_protected_ips)
            dst_internal = self._ip_in_range(dest_ip, fw.internal_protected_ips)
            dst_external = self._ip_in_range(dest_ip, fw.external_protected_ips)
            
            if src_internal or src_external:
                source_matches.append((fw, src_internal))
            if dst_internal or dst_external:
                dest_matches.append((fw, dst_internal))
        
        # 优先匹配：源和目的都在同一个防火墙
        for src_fw, src_internal in source_matches:
            for dst_fw, dst_internal in dest_matches:
                if src_fw.id == dst_fw.id:
                    if src_internal and dst_internal:
                        return (src_fw, 'same_firewall')
                    elif src_internal:
                        return (src_fw, 'outbound')
                    elif dst_internal:
                        return (src_fw, 'inbound')
        
        # 其次：源在某个防火墙的内部网段（出向）
        for fw, is_internal in source_matches:
            if is_internal:
                return (fw, 'outbound')
        
        # 最后：目的在某个防火墙的内部网段（入向）
        for fw, is_internal in dest_matches:
            if is_internal:
                return (fw, 'inbound')
        
        return (None, None)
    
    def _ip_in_range(self, ip_str: str, range_str: str) -> bool:
        """检查IP是否在范围内"""
        if not range_str:
            return False
        
        try:
            # 提取第一个IP（处理范围、掩码）
            ip = self._extract_first_ip(ip_str)
            ip_obj = ipaddress.ip_address(ip)
            
            # 遍历范围
            for line in range_str.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    # 尝试作为网络段
                    network = ipaddress.ip_network(line, strict=False)
                    if ip_obj in network:
                        return True
                except:
                    pass
            
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


class PolicyMergerV2:
    """策略合并器 V2 - 三步合并算法"""
    
    @staticmethod
    def merge_policies(policies: List[Dict]) -> List[Dict]:
        """
        三步合并：
        1. 合并端口（相同源+目的 → 合并端口）
        2. 合并目的地址（相同源+端口 → 合并目的）
        3. 合并源地址（相同目的+端口 → 合并源）
        """
        if not policies:
            return []
        
        # 第一步：合并端口
        policies = PolicyMergerV2._merge_by_service(policies)
        
        # 第二步：合并目的地址
        policies = PolicyMergerV2._merge_by_dest(policies)
        
        # 第三步：合并源地址
        policies = PolicyMergerV2._merge_by_source(policies)
        
        return policies
    
    @staticmethod
    def _merge_by_service(policies: List[Dict]) -> List[Dict]:
        """第一步：合并端口（相同源+目的 → 合并端口）"""
        merged = {}
        
        for p in policies:
            key = (p['source_ip'], p['dest_ip'], p['action'])
            if key in merged:
                # 合并端口
                merged[key]['services'].append(p['service'])
            else:
                # 保留第一个策略的所有字段
                merged[key] = p.copy()
                merged[key]['services'] = [p['service']]
        
        # 转换回列表
        result = []
        for item in merged.values():
            item['service'] = ','.join(item['services'])
            del item['services']
            result.append(item)
        
        return result
    
    @staticmethod
    def _merge_by_dest(policies: List[Dict]) -> List[Dict]:
        """第二步：合并目的地址（相同源+端口 → 合并目的）"""
        merged = {}
        
        for p in policies:
            key = (p['source_ip'], p['service'], p['action'])
            if key in merged:
                # 合并目的IP
                merged[key]['dest_ips'].append(p['dest_ip'])
            else:
                # 保留第一个策略的所有字段
                merged[key] = p.copy()
                merged[key]['dest_ips'] = [p['dest_ip']]
        
        # 转换回列表
        result = []
        for item in merged.values():
            item['dest_ip'] = '\n'.join(item['dest_ips'])
            del item['dest_ips']
            result.append(item)
        
        return result
    
    @staticmethod
    def _merge_by_source(policies: List[Dict]) -> List[Dict]:
        """第三步：合并源地址（相同目的+端口 → 合并源）"""
        merged = {}
        
        for p in policies:
            key = (p['dest_ip'], p['service'], p['action'])
            if key in merged:
                # 合并源IP
                merged[key]['source_ips'].append(p['source_ip'])
            else:
                # 保留第一个策略的所有字段
                merged[key] = p.copy()
                merged[key]['source_ips'] = [p['source_ip']]
        
        # 转换回列表
        result = []
        for item in merged.values():
            item['source_ip'] = '\n'.join(item['source_ips'])
            del item['source_ips']
            result.append(item)
        
        return result
