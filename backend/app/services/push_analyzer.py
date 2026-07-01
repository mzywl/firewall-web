"""
app/services/push_analyzer.py
标准策略引擎，执行基于真实数据的 6 要素比对复用计算
"""
from __future__ import annotations

import ipaddress
import re
from typing import Dict, List, Any


class StandardPolicyEngine:
    """标准化的策略 6 要素提取与复用引擎"""

    def __init__(self, resolved_device_rules: List[Dict[str, Any]]):
        """传入通过 Resolver 还原为真实 IP 后的设备配置列表"""
        self.device_rules = resolved_device_rules

    def standardize_db_request(self, raw_policy: Any) -> Dict[str, Any]:
        """将数据库 Model 提纯为标准比对字典"""
        src_ips = self._split_ips(raw_policy.source_ip)
        dst_ips = self._split_ips(raw_policy.dest_ip)

        return {
            "policy_id": raw_policy.id,
            "rule_name": f"O{raw_policy.order.order_no}-P{raw_policy.id}",
            "src_ips": src_ips if src_ips else ["0.0.0.0/0"],
            "dst_ips": dst_ips if dst_ips else ["0.0.0.0/0"],
            "ports": raw_policy.service.split() if raw_policy.service else ["ANY"],
            "src_zone": raw_policy.device_source_zone or "any",
            "dst_zone": raw_policy.device_dest_zone or "any",
            "valid_until": raw_policy.usage_time or "长期"
        }

    def match_reusability(self, std_req: Dict[str, Any]) -> Dict[str, Any]:
        """核心算法：计算工单需求是否落在某个现有策略中"""
        for rule in self.device_rules:
            # 1. 区域检查
            if rule['src_zone'] != std_req['src_zone'] or rule['dst_zone'] != std_req['dst_zone']:
                continue

            # 2. 集合包含算法 (请求的每一个要素都必须被设备老策略包含)
            if not self._is_ip_subset(std_req['src_ips'], rule['src_ips']): continue
            if not self._is_ip_subset(std_req['dst_ips'], rule['dst_ips']): continue
            if not self._is_port_subset(std_req['ports'], rule['ports']): continue

            # 3. 拦截到复用规则，进行时间判定
            if self._is_time_covered(std_req['valid_until'], rule['valid_until']):
                return {"mode": "FULL_MATCH", "reused_rule": rule['name'], "action": "SKIP"}
            else:
                return {"mode": "TIME_UPDATE", "reused_rule": rule['name'], "action": "UPDATE_TIME"}

        return {"mode": "NEW_RULE", "reused_rule": None, "action": "GENERATE"}

    # ================= 辅助比对方法 =================

    @staticmethod
    def _split_ips(s: str) -> List[str]:
        if not s: return []
        return [p for p in re.split(r"[\s,;]+", s.strip()) if p]

    @staticmethod
    def _is_ip_subset(req_ips: List[str], exist_ips: List[str]) -> bool:
        if not req_ips: return True
        if any(ex.lower() in ("any", "0.0.0.0/0") for ex in exist_ips): return True

        for r in req_ips:
            try: r_net = ipaddress.ip_network(r.strip(), strict=False)
            except ValueError: continue

            covered = False
            for ex in exist_ips:
                try: ex_net = ipaddress.ip_network(ex.strip(), strict=False)
                except ValueError: continue
                if r_net.subnet_of(ex_net):
                    covered = True
                    break
            if not covered: return False
        return True

    @staticmethod
    def _is_port_subset(req_ports: List[str], exist_ports: List[str]) -> bool:
        if not req_ports: return True
        if not exist_ports: return False
        exist_lower = [s.lower() for s in exist_ports if s]
        if any(s == "any" for s in exist_lower): return True

        for rp in req_ports:
            rp_lower = rp.lower()
            if not any((rp_lower in el) or (el in rp_lower) for el in exist_lower):
                return False
        return True

    @staticmethod
    def _is_time_covered(req_time: str, exist_time: str) -> bool:
        if not exist_time or exist_time.lower() in ("any", "always"): return True
        if not req_time: return True
        return req_time.strip() == exist_time.strip()