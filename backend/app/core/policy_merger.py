"""
策略合并优化算法（全量压缩版）
"""
from typing import List, Dict, Any
from collections import defaultdict


class PolicyMerger:
    """策略合并优化器"""

    def __init__(self):
        self.merged_policies = []

    def merge_policies(self, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并策略
        规则：
        1. 相同源IP、目的IP、协议、使用时间的策略合并端口
        2. 连续端口范围智能压缩 (如 80,81,82 -> 80-82)
        3. 跨策略无序多端口全量拼接 (如 80 和 443 -> 80,443)
        """
        if not policies:
            return []

        # 按 (源IP, 目的IP, 协议, 有效期) 联合四维度分组
        groups = defaultdict(list)

        for policy in policies:
            # 统一对输入的 IP 做一次轻量级清洗标准化，防止因"/32"后缀有无导致分组失败
            src_ip = self._norm_ip_for_key(policy.get('source_ip', ''))
            dst_ip = self._norm_ip_for_key(policy.get('dest_ip', ''))
            proto = self._extract_protocol(policy.get('service', ''))
            usage_time = str(policy.get('usage_time', '长期')).strip()

            key = (src_ip, dst_ip, proto, usage_time)
            groups[key].append(policy)

        merged = []

        for key, group in groups.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                # 触发多策略深度融合压缩
                merged.extend(self._merge_group(group))

        return merged

    def _merge_group(self, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并同组多条策略的端口"""
        proto = self._extract_protocol(policies[0].get('service', ''))

        # 1. 全量提取该组下的所有端口数字
        ports = []
        for policy in policies:
            service = policy.get('service', '')
            ports.extend(self._extract_ports(service))

        if not ports:
            # 如果没提取出数字端口（如 "any"），保留原样
            return policies

        # 2. 去重并排序
        ports = sorted(set(ports))

        # 3. 连续端口段压缩优化（返回如 ['80', '443', '8080-8085']）
        port_ranges = self._optimize_port_ranges(ports)

        # 4. 彻底修复原版 len==1 的限制：将所有优化后的端口段用逗号重新聚合成标准字符串
        #    并根据协议类型重新附带标准前缀（如果是 UDP，则重新附带 "UDP:" 标记）
        if proto == 'udp':
            combined_service = ",".join([f"UDP:{pr}" for pr in port_ranges])
        else:
            combined_service = ",".join(port_ranges)

        # 5. 组装合并后的全新策略主体
        merged_policy = policies[0].copy()
        merged_policy['service'] = combined_service
        merged_policy['is_merged'] = 1

        # 收集溯源 ID（用于向主表关联更新 merged_policy_id）
        merged_policy['merged_from'] = [p.get('id') for p in policies if p.get('id') is not None]

        return [merged_policy]

    def _extract_protocol(self, service: str) -> str:
        """提取协议特征"""
        if not service:
            return 'tcp'  # 默认降级为 tcp

        service_lower = service.lower()
        if 'udp' in service_lower:
            return 'udp'
        elif 'icmp' in service_lower:
            return 'icmp'
        else:
            return 'tcp'  # 默认归类为 tcp

    def _extract_ports(self, service: str) -> List[int]:
        """从服务字段精准剥离纯数字端口"""
        if not service:
            return []

        ports = []
        # 清洗由于各类格式化器引入的所有已知前缀/后缀干扰
        s_clean = service.upper()
        for prefix in ['TCP/', 'UDP/', 'TCP:', 'UDP:']:
            s_clean = s_clean.replace(prefix, '')

        parts = s_clean.split(',')
        for part in parts:
            part = part.strip()
            if not part:
                continue

            if '-' in part:
                try:
                    start, end = part.split('-')
                    start_port = int(start.strip())
                    end_port = int(end.strip())
                    if start_port <= end_port:
                        ports.extend(range(start_port, end_port + 1))
                except ValueError:
                    pass
            else:
                try:
                    ports.append(int(part))
                except ValueError:
                    pass
        return ports

    def _optimize_port_ranges(self, ports: List[int]) -> List[str]:
        """优化连续端口范围"""
        if not ports:
            return []

        ranges = []
        start = ports[0]
        end = ports[0]

        for i in range(1, len(ports)):
            if ports[i] == end + 1:
                end = ports[i]
            else:
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{end}")
                start = ports[i]
                end = ports[i]

        if start == end:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{end}")

        return ranges

    # ============================================================
    #                      语义级冗余检测层
    # ============================================================

    def detect_redundant(self, policies: List[Dict[str, Any]]) -> List[int]:
        """
        语义级冗余策略判定
        返回被完全包容、应当被标记或剔除的冗余策略 ID 列表
        """
        redundant_ids = []

        # 为了提高比对效率，前置将所有策略的语义 Key 提取并标准化
        parsed_meta = []
        for p in policies:
            parsed_meta.append({
                'id': p.get('id'),
                'src': self._norm_ip_for_key(p.get('source_ip', '')),
                'dst': self._norm_ip_for_key(p.get('dest_ip', '')),
                'ports_set': set(self._extract_ports(p.get('service', ''))),
                'proto': self._extract_protocol(p.get('service', '')),
                'time': str(p.get('usage_time', '长期')).strip()
            })

        for i, p1 in enumerate(parsed_meta):
            for j, p2 in enumerate(parsed_meta):
                if i == j:
                    continue
                # 如果 p2 的四维度完全被 p1 覆盖，则 p2 属于冗余策略
                if (p1['src'] == p2['src'] and
                    p1['dst'] == p2['dst'] and
                    p1['proto'] == p2['proto'] and
                    p1['time'] == p2['time'] and
                    p2['ports_set'].issubset(p1['ports_set'])):  # 👈 端口子集全包容判定

                    if p2['id'] is not None:
                        redundant_ids.append(p2['id'])

        return list(set(redundant_ids))

    @staticmethod
    def _norm_ip_for_key(ip_str: str) -> str:
        """归一化 IP 辅助工具：去除首尾空格、去除单 IP 末尾冗余的 /32"""
        if not ip_str:
            return ""
        s = str(ip_str).strip().replace(' ', '')
        if s.endswith('/32'):
            return s[:-3]
        return s