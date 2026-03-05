"""
策略合并优化算法
"""
from typing import List, Dict, Any
from collections import defaultdict
import ipaddress


class PolicyMerger:
    """策略合并优化器"""
    
    def __init__(self):
        self.merged_policies = []
    
    def merge_policies(self, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并策略
        规则：
        1. 相同源IP、目的IP、协议的策略合并端口
        2. 连续端口范围优化
        3. 标记冗余策略
        """
        # 按 (源IP, 目的IP, 协议) 分组
        groups = defaultdict(list)
        
        for policy in policies:
            key = (
                policy.get('source_ip', ''),
                policy.get('dest_ip', ''),
                self._extract_protocol(policy.get('service', ''))
            )
            groups[key].append(policy)
        
        merged = []
        
        for key, group in groups.items():
            if len(group) == 1:
                # 单个策略，不需要合并
                merged.append(group[0])
            else:
                # 多个策略，尝试合并
                merged_policy = self._merge_group(group)
                merged.extend(merged_policy)
        
        return merged
    
    def _merge_group(self, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并同组策略"""
        # 提取所有端口
        ports = []
        for policy in policies:
            service = policy.get('service', '')
            ports.extend(self._extract_ports(service))
        
        # 去重并排序
        ports = sorted(set(ports))
        
        # 优化端口范围
        port_ranges = self._optimize_port_ranges(ports)
        
        # 如果可以合并成一个策略
        if len(port_ranges) == 1:
            merged_policy = policies[0].copy()
            merged_policy['service'] = port_ranges[0]
            merged_policy['is_merged'] = 1
            merged_policy['merged_from'] = [p.get('id') for p in policies]
            return [merged_policy]
        
        # 否则返回原策略
        return policies
    
    def _extract_protocol(self, service: str) -> str:
        """提取协议（tcp/udp/icmp）"""
        if not service:
            return 'any'
        
        service_lower = service.lower()
        if 'tcp' in service_lower:
            return 'tcp'
        elif 'udp' in service_lower:
            return 'udp'
        elif 'icmp' in service_lower:
            return 'icmp'
        else:
            return 'any'
    
    def _extract_ports(self, service: str) -> List[int]:
        """从服务字段提取端口列表"""
        if not service:
            return []
        
        ports = []
        
        # 移除协议前缀（tcp/udp）
        service = service.replace('tcp/', '').replace('udp/', '').replace('TCP/', '').replace('UDP/', '')
        
        # 处理多个端口（逗号分隔）
        parts = service.split(',')
        
        for part in parts:
            part = part.strip()
            
            # 处理端口范围（例如：8080-8090）
            if '-' in part:
                try:
                    start, end = part.split('-')
                    start_port = int(start.strip())
                    end_port = int(end.strip())
                    ports.extend(range(start_port, end_port + 1))
                except:
                    pass
            else:
                # 单个端口
                try:
                    ports.append(int(part))
                except:
                    pass
        
        return ports
    
    def _optimize_port_ranges(self, ports: List[int]) -> List[str]:
        """优化端口范围"""
        if not ports:
            return []
        
        ranges = []
        start = ports[0]
        end = ports[0]
        
        for i in range(1, len(ports)):
            if ports[i] == end + 1:
                # 连续端口
                end = ports[i]
            else:
                # 不连续，保存当前范围
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{end}")
                start = ports[i]
                end = ports[i]
        
        # 保存最后一个范围
        if start == end:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{end}")
        
        return ranges
    
    def detect_redundant(self, policies: List[Dict[str, Any]]) -> List[int]:
        """
        检测冗余策略
        返回冗余策略的 ID 列表
        """
        redundant_ids = []
        
        for i, policy1 in enumerate(policies):
            for j, policy2 in enumerate(policies):
                if i >= j:
                    continue
                
                # 检查是否完全包含
                if self._is_redundant(policy1, policy2):
                    redundant_ids.append(policy2.get('id'))
        
        return list(set(redundant_ids))
    
    def _is_redundant(self, policy1: Dict[str, Any], policy2: Dict[str, Any]) -> bool:
        """检查 policy2 是否被 policy1 完全包含"""
        # 简化版：只检查源IP、目的IP、服务是否相同
        return (
            policy1.get('source_ip') == policy2.get('source_ip') and
            policy1.get('dest_ip') == policy2.get('dest_ip') and
            policy1.get('service') == policy2.get('service')
        )
