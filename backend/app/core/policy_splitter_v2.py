"""
策略拆分与合并模块 V2 - 高性能完全重写版
"""
from typing import List, Dict, Tuple, Optional, Set
import ipaddress
import re
from sqlalchemy.orm import Session
from app.models import Firewall

# 假设复用你前序编写的端口压缩优化器
# from app.services.policy_merger import PolicyMerger


class PolicySplitterV2:
    """策略拆分器 V2 - 将一行策略拆分成多个独立的单IP/网段策略，精准探测防火墙边界"""

    def __init__(self, db: Session):
        self.db = db
        # 排序：边界防火墙(is_zone_boundary=1)排前面，确保 region 内 NAT 状态优先建立
        self.firewalls = db.query(Firewall).filter(
            Firewall.is_active == 1
        ).order_by(Firewall.is_zone_boundary.desc(), Firewall.id.asc()).all()

    def split_policy_to_single_ips(self, source_ips_str: str, dest_ips_str: str,
                                     service: str, action: str, usage_time: str = "长期") -> List[Dict]:
        """
        将一行可能夹杂多IP的复杂策略拆分成多条单IP对的笛卡尔积条目
        """
        result = []

        # 拆分源IP和目的IP（前置防空、防杂质清洗）
        source_ips = self._split_ips(source_ips_str)
        dest_ips = self._split_ips(dest_ips_str)

        # 笛卡尔积矩阵展开：每个源IP × 每个目的IP = 独立分析单元
        for src_ip in source_ips:
            for dst_ip in dest_ips:
                # 匹配所有相关的防火墙及流量方向
                matched_firewalls = self._match_all_firewalls(src_ip, dst_ip)

                # 找 src/dst 对应的 zone_name (用于 merger 分组 key + warning 消息)
                src_zone_name = None
                dst_zone_name = None
                for fw, _direction in matched_firewalls:
                    zid = self._find_zone_id_by_ip(src_ip, fw)
                    if zid is not None:
                        for z in fw.zones:
                            if z.id == zid:
                                src_zone_name = z.zone_name
                                break
                        if src_zone_name:
                            break
                for fw, _direction in matched_firewalls:
                    zid = self._find_zone_id_by_ip(dst_ip, fw)
                    if zid is not None:
                        for z in fw.zones:
                            if z.id == zid:
                                dst_zone_name = z.zone_name
                                break
                        if dst_zone_name:
                            break

                if not matched_firewalls:
                    # 没有任何物理资产网段覆盖该单IP对
                    result.append({
                        'source_ip': src_ip,
                        'dest_ip': dst_ip,
                        'service': service,
                        'action': action,
                        'usage_time': usage_time,
                        'firewall': None,
                        'direction': None,
                        'not_pushed_reason': '未匹配到任何防火墙',
                        'src_zone_name': src_zone_name,
                        'dst_zone_name': dst_zone_name,
                    })
                else:
                    # 为每个被波及的物理墙生成独立的推送条目
                    for firewall, direction in matched_firewalls:
                        policy_item = {
                            'source_ip': src_ip,
                            'dest_ip': dst_ip,
                            'service': service,
                            'action': action,
                            'usage_time': usage_time,
                            'firewall': firewall,
                            'direction': direction,
                            'not_pushed_reason': None,
                            'src_zone_name': src_zone_name,
                            'dst_zone_name': dst_zone_name,
                        }

                        # 基于墙体属性执行策略安全拦截拦截
                        # 新设计 (2026-06-22): allow_same_firewall_push 字段已删除, 同墙默认允许
                        if direction == 'same_firewall':
                            pass  # 同墙策略不再受字段开关限制
                        elif direction == 'cross_internal':
                            policy_item['not_pushed_reason'] = f'源IP在{firewall.name}内部，目的IP在其他防火墙内部，跨防火墙内部通信不推送'
                        elif direction == 'same_zone_l2':
                            # 新增 (2026-06-22): 同墙同 zone L2 互通, fw 看不到流量
                            # 用 warning_reason (不是 not_pushed_reason) → chain_planner 只加到 warnings,
                            # 不进 not_pushed 列表 (用户要求 "只提示在异常里")
                            policy_item['firewall'] = None
                            policy_item['direction'] = None
                            zone_label = src_zone_name or 'unknown'
                            policy_item['warning_reason'] = (
                                f'同墙同 zone (fw={firewall.name}, zone={zone_label}) L2 互通, '
                                f'fw 看不到流量, 不推送'
                            )

                        result.append(policy_item)

        return result

    def _split_ips(self, ip_str: str) -> List[str]:
        """拆分IP字符串为干净、无杂质的单个元素列表"""
        if not ip_str:
            return []

        ips = []
        # 统一处理常见分隔符换行、逗号、分号混排
        normalized = ip_str.replace('\r\n', '\n').replace(',', '\n').replace(';', '\n').replace('；', '\n')
        for part in normalized.split('\n'):
            part = part.strip()
            if part:
                ips.append(part)
        return ips

    def _match_all_firewalls(self, source_ip: str, dest_ip: str) -> List[Tuple[Firewall, str]]:
        """
        核心物理矩阵匹配：判定 IP 对在全网防火墙中的路由拓扑方向

        返回 (firewall, direction) 元组列表。direction 取值:
          - 'same_firewall':  同墙跨 zone (fw 内部跨 zone 隔离)
          - 'same_zone_l2':  同墙同 zone (L2 互通, fw 看不到流量, 不推送)
          - 'cross_internal': 跨墙同 region 内部通信 (不推送)
          - 'outbound':     流量从 fw 出
          - 'inbound':      流量进 fw
        """
        result = []
        # source_matches / dest_matches: [(fw, is_internal, zone_id_or_None)]
        source_matches = []
        dest_matches = []

        for fw in self.firewalls:
            # 新设计: 用 FirewallZone.protected_ips 替代旧的 internal/external_protected_ips
            # internal 判定: zone.connect_region == fw.belong_region
            src_internal = self._ip_in_internal_zones(source_ip, fw)
            src_external = self._ip_in_external_zones(source_ip, fw)
            dst_internal = self._ip_in_internal_zones(dest_ip, fw)
            dst_external = self._ip_in_external_zones(dest_ip, fw)

            # 找具体 zone_id (用于同墙同 zone 判定)
            src_zone_id = self._find_zone_id_by_ip(source_ip, fw)
            dst_zone_id = self._find_zone_id_by_ip(dest_ip, fw)

            if src_internal or src_external:
                source_matches.append((fw, src_internal, src_zone_id))
            if dst_internal or dst_external:
                dest_matches.append((fw, dst_internal, dst_zone_id))

        # 1. 优先捕获同墙规则
        same_firewall_found = False
        for src_fw, src_internal, src_zone_id in source_matches:
            for dst_fw, dst_internal, dst_zone_id in dest_matches:
                if src_fw.id == dst_fw.id and src_internal and dst_internal:
                    # 新增 (2026-06-22): 同墙同 zone 细分
                    # 物理上 L2 互通不走 fw, 推了无意义, 标记 'same_zone_l2' 给调用方处理
                    if src_zone_id is not None and src_zone_id == dst_zone_id:
                        result.append((src_fw, 'same_zone_l2'))
                    else:
                        result.append((src_fw, 'same_firewall'))
                    same_firewall_found = True
                    break
            if same_firewall_found:
                break

        if same_firewall_found:
            return result

        # 2. 捕获同 region 下的跨内部核心隔离
        for src_fw, src_internal, _ in source_matches:
            if src_internal:
                for dst_fw, dst_internal, _ in dest_matches:
                    if dst_internal and src_fw.id != dst_fw.id and getattr(src_fw, 'belong_region', '') == getattr(dst_fw, 'belong_region', 'default'):
                        result.append((src_fw, 'cross_internal'))
                        return result  # 拦截阻断

        # 3. 正常出向捕获
        for fw, is_internal, _ in source_matches:
            if is_internal:
                result.append((fw, 'outbound'))

        # 4. 正常入向捕获
        for fw, is_internal, _ in dest_matches:
            if is_internal:
                result.append((fw, 'inbound'))

        return result

    def _find_zone_id_by_ip(self, ip_str: str, fw: Firewall) -> Optional[int]:
        """找 IP 命中的 FirewallZone.id (返回 None if 没命中)

        用于同墙同 zone 细分判定 (2026-06-22): 同 src_zone_id 和 dst_zone_id 时
        物理上 L2 互通, fw 看不到流量, 推送无意义。
        """
        if not ip_str or not fw.zones:
            return None
        try:
            ip = self._extract_first_ip(ip_str)
            ip_obj = ipaddress.ip_address(ip)
        except Exception:
            return None
        for zone in fw.zones:
            if not zone.protected_ips:
                continue
            for line in zone.protected_ips.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                try:
                    if ip_obj in ipaddress.ip_network(line, strict=False):
                        return zone.id
                except Exception:
                    continue
        return None

    def _ip_in_range(self, ip_str: str, range_str: str) -> bool:
        if not range_str:
            return False
        try:
            ip = self._extract_first_ip(ip_str)
            ip_obj = ipaddress.ip_address(ip)

            for line in range_str.strip().split('\n'):
                line = line.strip()
                if not line: continue
                try:
                    if ip_obj in ipaddress.ip_network(line, strict=False):
                        return True
                except:
                    continue
            return False
        except:
            return False

    def _ip_in_internal_zones(self, ip_str: str, fw: Firewall) -> bool:
        """新设计: IP 落在 firewall 内部 zones (zone.connect_region == fw.belong_region)"""
        if not fw.zones or not fw.belong_region:
            return False
        try:
            ip = self._extract_first_ip(ip_str)
            ip_obj = ipaddress.ip_address(ip)
        except Exception:
            return False
        for zone in fw.zones:
            if zone.connect_region != fw.belong_region:
                continue
            if zone.protected_ips and self._ip_in_range(ip_str, zone.protected_ips):
                return True
        return False

    def _ip_in_external_zones(self, ip_str: str, fw: Firewall) -> bool:
        """新设计: IP 落在 firewall 外部 zones (zone.connect_region != fw.belong_region)"""
        if not fw.zones or not fw.belong_region:
            return False
        try:
            ip = self._extract_first_ip(ip_str)
            ip_obj = ipaddress.ip_address(ip)
        except Exception:
            return False
        for zone in fw.zones:
            if zone.connect_region == fw.belong_region:
                continue
            if zone.protected_ips and self._ip_in_range(ip_str, zone.protected_ips):
                return True
        return False

    def _extract_first_ip(self, ip_str: str) -> str:
        if not ip_str: return ""
        if '-' in ip_str: return ip_str.split('-')[0].strip()
        if '/' in ip_str: return ip_str.split('/')[0].strip()
        return ip_str.strip()


class PolicyMergerV2:
    """策略合并器 V2 - 高性能无序多维聚合三步法算法"""

    @staticmethod
    def merge_policies(policies: List[Dict]) -> List[Dict]:
        """
        三步安全无序聚合：
        1. 聚合端口：相同 (源IP, 目的IP, 墙, 方向, src_zone, dst_zone, 有效期) -> 端口去重
        2. 聚合目的：相同 (源IP, 端口集, 墙, 方向, src_zone, dst_zone, 有效期) -> 目的IP合并
        3. 聚合源：  相同 (目的IP集, 端口集, 墙, 方向, src_zone, dst_zone, 有效期) -> 源IP合并

        端口字段: 直接用 splitter (PortFormatter) 已经格式化好的字符串,
                  例如 "138-139\n445"。聚合用 Set[str] 做语义去重, 渲染时直接 join。
                  不再做端口连续区间检测, splitter 已经做完了。

        字段名约定:
        - 输入: 兼容 'usage_time'(英) 和 '使用时间'(中) 两种 key, 中文优先 (preview.py 落的中文 key)
        - 输出: 同时保留 'usage_time'(英, 内部用) 和 '使用时间'(中, 前端用), 便于上下游两种消费者
        - 保留所有非分组字段 (source_zone, dest_zone, original_policy_id, nat_info, pass_through,
          original_data, id 等) — 这些是前端展示 + 后续 NAT re-analyze 必需的 metadata,
          早期版本会丢光导致 Preview 页所有 NAT 列都空
        """
        if not policies:
            return []

        # 将原始数据标准化，转化为易于做集合计算的内部格式
        meta_items = []
        for p in policies:
            # 中文 key 优先, 兼容英文 key (PolicyMerger 旧版用 usage_time, preview.py 用 使用时间)
            usage_time = p.get('使用时间') or p.get('usage_time') or '长期'
            meta_item = {
                'src_set': {p['source_ip']},
                'dst_set': {p['dest_ip']},
                'port_tokens': PolicyMergerV2._split_port_tokens(p['service']),
                'firewall': p.get('firewall'),
                'direction': p.get('direction'),
                'action': p.get('action'),
                'usage_time': usage_time,
                'not_pushed_reason': p.get('not_pushed_reason'),
                # 新增 (2026-06-22): zone 维度加入分组 key, 防止跨 zone 的 sp 错误合并
                'src_zone_name': p.get('src_zone_name'),
                'dst_zone_name': p.get('dst_zone_name'),
            }
            # 透传所有非分组字段 (source_zone, dest_zone, original_policy_id, nat_info,
            # pass_through, original_data, id 等)
            # — 这些是前端展示 + preview.py 后续 NAT re-analyze 必需的 metadata
            # — 必须在这里就带上, _stage_merge_* 用 item.copy() 会保留下来,
            #   _render_to_final_format 再透传出去
            for k, v in p.items():
                if k not in ('source_ip', 'dest_ip', 'service', 'firewall', 'direction',
                             'action', 'usage_time', 'not_pushed_reason', '使用时间',
                             'src_zone_name', 'dst_zone_name'):
                    meta_item[k] = v
            meta_items.append(meta_item)

        # 第一步：相同源+目的+墙 -> 合并端口组
        meta_items = PolicyMergerV2._stage_merge_services(meta_items)

        # 第二步：相同源+端口组+墙 -> 合并目的地址组
        meta_items = PolicyMergerV2._stage_merge_dests(meta_items)

        # 第三步：相同目的组+端口组+墙 -> 合并源地址组
        meta_items = PolicyMergerV2._stage_merge_sources(meta_items)

        # 将无序集合还原成符合业务调用规范的文本字符串格式
        return PolicyMergerV2._render_to_final_format(meta_items)

    @staticmethod
    def _stage_merge_services(items: List[Dict]) -> List[Dict]:
        merged = {}
        for item in items:
            # 基础路由属性元组作为散列 Key
            # 新增 (2026-06-22): 加 src_zone_name/dst_zone_name 防止跨 zone 的 sp 错误合并
            key = (
                frozenset(item['src_set']),
                frozenset(item['dst_set']),
                item['firewall'].id if item['firewall'] else None,
                item['direction'],
                item.get('src_zone_name'),
                item.get('dst_zone_name'),
                item['action'],
                item['usage_time'],
                item['not_pushed_reason']
            )
            if key in merged:
                merged[key]['port_tokens'].update(item['port_tokens'])
            else:
                merged[key] = item.copy()
        return list(merged.values())

    @staticmethod
    def _stage_merge_dests(items: List[Dict]) -> List[Dict]:
        merged = {}
        for item in items:
            # 新增 (2026-06-22): 加 src_zone_name/dst_zone_name 防止跨 zone 的 sp 错误合并
            key = (
                frozenset(item['src_set']),
                frozenset(item['port_tokens']), # 👈 端口 token 作为不可变集合参与哈希，彻底解决顺序干扰
                item['firewall'].id if item['firewall'] else None,
                item['direction'],
                item.get('src_zone_name'),
                item.get('dst_zone_name'),
                item['action'],
                item['usage_time'],
                item['not_pushed_reason']
            )
            if key in merged:
                merged[key]['dst_set'].update(item['dst_set'])
            else:
                merged[key] = item.copy()
        return list(merged.values())

    @staticmethod
    def _stage_merge_sources(items: List[Dict]) -> List[Dict]:
        """
        第三步: 相同 (目的组, 端口组, 墙, 方向, ...) -> 合并源组

        D 方案严格版 (2026-06-19): SNAT 透传字段清理
          - original_source_ip 字段删除 (fw14 src 已经是 SNAT 后 IP, 不需要备份原始 IP)
          - via_firewall 字段删除 (fw6 SNAT 行已经标了转换信息, fw14 不需要重复)
          - 直连 IP (无 SNAT 转换) → unmatched, 不会进 fw inbound 合并, 所以不需要
            _pick_nat_info 优先保留含 SNAT 的 sp (fw inbound 永远是单 sp 上墙)
        """
        merged = {}
        for item in items:
            # 新增 (2026-06-22): 加 src_zone_name/dst_zone_name 防止跨 zone 的 sp 错误合并
            key = (
                frozenset(item['dst_set']), # 👈 已经归一化排好序的目的集合作为哈希 Key
                frozenset(item['port_tokens']),
                item['firewall'].id if item['firewall'] else None,
                item['direction'],
                item.get('src_zone_name'),
                item.get('dst_zone_name'),
                item['action'],
                item['usage_time'],
                item['not_pushed_reason']
            )
            if key in merged:
                merged[key]['src_set'].update(item['src_set'])
            else:
                merged[key] = item.copy()
        return list(merged.values())

    @staticmethod
    def _render_to_final_format(items: List[Dict]) -> List[Dict]:
        """将内部集合对象高保真渲染为输出文本

        端口字段: 直接 splitter 输出 + sorted + join。
        不再做端口连续区间检测 — splitter/PortFormatter 已经做完。
        """
        result = []
        for item in items:
            src_str = "\n".join(sorted(item['src_set']))
            dst_str = "\n".join(sorted(item['dst_set']))

            # D 方案: service 直接用 splitter (PortFormatter) 已格式化的输出格式 (换行分隔),
            # 不要重新 sort+join. splitter/PortFormatter 已经做了: 端口连续区间检测 + 按端口数字排序.
            # 前端直接展示, 不再处理.
            service_str = "\n".join(item['port_tokens']) if item['port_tokens'] else "any"

            # 分组用的字段 (这些是从 item 内部集合渲染出来的, 不能保留原值)
            GROUPING_FIELDS = {
                'source_ip', 'dest_ip', 'service',
                'firewall', 'direction', 'action', 'usage_time', 'not_pushed_reason',
                'src_set', 'dst_set', 'port_tokens',  # 内部集合字段
            }

            rendered = {
                'source_ip': src_str,
                'dest_ip': dst_str,
                'service': service_str,
                'action': item['action'],
                'firewall': item['firewall'],
                'direction': item['direction'],
                'not_pushed_reason': item['not_pushed_reason'],
            }
            # 时间字段双 key 都输出: usage_time (英文, 兼容 PolicyMerger) + 使用时间 (中文, 适配前端)
            rendered['usage_time'] = item['usage_time']
            rendered['使用时间'] = item['usage_time']

            # D 方案: original_source_ip / via_firewall 字段已删除
            # (fw14 src 已经是 SNAT 后 IP, 不需要备份原始 IP;
            #  fw6 SNAT 行已经标了转换信息, fw14 不需要重复 via_firewall)

            # 透传所有非分组字段 (source_zone, dest_zone, original_policy_id, nat_info,
            # nat_policies, pass_through, original_data, id 等)
            # — 前端 PreviewPolicy 类型需要这些字段才能渲染 NAT 列 / 时间列 / 区域列
            for k, v in item.items():
                if k not in GROUPING_FIELDS and k not in rendered and k not in ('使用时间', 'original_set'):
                    rendered[k] = v

            result.append(rendered)
        return result

    @staticmethod
    def _split_port_tokens(service: str) -> Set[str]:
        """把 splitter 已格式化的 service 字符串拆成 port token set

        splitter (PortFormatter) 已经把 Excel 端口规整成统一格式 (例如 "138-139\\n445"),
        这里只负责按分隔符拆开, 不做数值解析/区间展开/连续端口合并 —
        那些 splitter 都做完了, 我们只复用它的输出。
        """
        if not service or service.strip().lower() == 'any':
            return set()
        # 兼容 PortFormatter 的 \\n 分隔 + 兼容遗留 , 分隔
        tokens = re.split(r'[,\s]+', service.strip())
        return {t for t in tokens if t}