"""
PrePushAnalyzer - 预推送复用与脚本分析器 (H3C 6要素严格校验版)

6 要素: source_zone × dest_zone × source_ip × dest_ip × service × time
3 种归宿 (match_mode):
  - FULL_MATCH: 6 要素全部包容, 跳过 (空 push_script)
  - TIME_UPDATE: zone/ip/port 全包容, 仅时间不包容, 生成修改老策略时间 CLI
  - NEW_RULE: 任何要素不匹配, 全新建

设计原则:
  - 一次性预解析 fw_cache (避免每条策略重复 parse)
  - 对象名扁平化: src_addrs 是 object name list, 需递归反查成 IP 列表
  - IP 包容: req_ip.subnet_of(exist_ip) — req 落在 exist 内才算
  - Port 包容: 简单字符串包含 (已足够覆盖 [80], [80-90] 这类)
  - Time 包容: 老策略时间 any/空/等于需求 → 包容

使用示例:
    analyzer = PrePushAnalyzer(fw_cache)
    for req_policy in requests:
        result = analyzer.analyze_single_policy(req_policy)
        # result["match_mode"], result["push_script"], result["audit_message"]
"""
from __future__ import annotations

import ipaddress
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PrePushAnalyzer:
    """预推送分析器 — 6 要素严格校验"""

    def __init__(self, fw_cache: Optional[Dict[str, Any]] = None):
        """
        fw_cache = {
            "rules": [
                {
                    "name": str,
                    "source_zone": str,
                    "dest_zone": str,
                    "src_addrs": List[str],       # object name 列表
                    "dst_addrs": List[str],
                    "services": List[str],
                    "schedule": Optional[str],    # time-range object name
                }
            ],
            "addresses": [
                {"name": str, "value": str, "members": List[str]}
            ],
            "time_ranges": [
                {"name": str, "text": str}     # 文本形式的时间定义
            ],
        }
        """
        self.fw_cache = fw_cache or {}
        self._addr_index: Dict[str, List[str]] = self._build_addr_index(
            self.fw_cache.get("addresses", [])
        )
        self._time_index: Dict[str, str] = self._build_time_index(
            self.fw_cache.get("time_ranges", [])
        )
        # 预解析每个 rule 的扁平 IP 列表 (递归解析 object group)
        self._rules_with_ips: List[Dict[str, Any]] = [
            {
                **rule,
                "source_ips": self._flatten_ips(rule.get("src_addrs") or []),
                "dest_ips": self._flatten_ips(rule.get("dst_addrs") or []),
                "schedule_text": self._resolve_schedule_text(
                    rule.get("schedule") or ""
                ),
            }
            for rule in self.fw_cache.get("rules", [])
        ]

    # ============================================================
    # 索引构建
    # ============================================================

    @staticmethod
    def _build_addr_index(addresses: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """AddressObject list → {name: [ip_or_member, ...]}

        value 是 IP/CIDR 字符串, members 是子对象名 (前缀 @) 或裸 IP
        不过滤 @ 前缀, 留给 _walk 区分递归 vs 当 IP
        """
        idx: Dict[str, List[str]] = {}
        for a in addresses:
            items: List[str] = []
            value = a.get("value") or ""
            if value:
                items.append(value)
            for m in a.get("members", []) or []:
                if m:
                    items.append(m)
            idx[a["name"]] = items
        return idx

    @staticmethod
    def _build_time_index(time_ranges: List[Dict[str, Any]]) -> Dict[str, str]:
        return {t["name"]: t.get("text", "") for t in time_ranges}

    def _flatten_ips(self, names: List[str], _seen: Optional[Set[str]] = None) -> List[str]:
        """object name 列表 → 扁平 IP 字符串列表 (递归解析 group)

        防环: 同一 name 在 _seen 里就跳过
        防深: _depth 由 _seen 大小间接限制
        """
        if _seen is None:
            _seen = set()
        out: Set[str] = set()
        for name in names:
            self._walk(name, out, _seen, depth=0)
        return list(out)

    def _walk(
        self, name: str, out: Set[str], _seen: Set[str], depth: int
    ) -> None:
        if depth > 5 or not name or name in _seen:
            return
        _seen.add(name)
        # 名字本身可能就是 IP/CIDR
        try:
            ipaddress.ip_network(name, strict=False)
            out.add(name)
            return
        except ValueError:
            pass
        # 查 addr 索引递归
        if name in self._addr_index:
            for ip_or_member in self._addr_index[name]:
                # 如果是 @group 引用, 名字是 @xxx
                if ip_or_member.startswith("@"):
                    self._walk(ip_or_member[1:], out, _seen, depth + 1)
                else:
                    self._walk(ip_or_member, out, _seen, depth + 1)
        # 名字未在 addr 索引里 (没拉到配置), 跳过

    def _resolve_schedule_text(self, name: str) -> str:
        """time-range object name → 文本形式 (空/any 则返回空)"""
        if not name:
            return ""
        if name.lower() in ("any", "always"):
            return ""
        return self._time_index.get(name, name)

    @staticmethod
    def _summarize_rule(rule: Dict[str, Any], schedule_text: str) -> str:
        """给前端展示的策略摘要"""
        parts = [
            f"源域={rule.get('source_zone', 'any')}",
            f"目的域={rule.get('dest_zone', 'any')}",
            f"源IP={','.join(rule.get('source_ips', []) or ['?'])[:60]}",
            f"目的IP={','.join(rule.get('dest_ips', []) or ['?'])[:60]}",
            f"服务={','.join(rule.get('services', []) or ['?'])}",
        ]
        if schedule_text:
            parts.append(f"时间={schedule_text[:30]}")
        return "; ".join(parts)

    # ============================================================
    # 主入口: 单条策略分析
    # ============================================================

    def analyze_single_policy(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        6 要素严格校验

        req = {
            "device_source_zone", "device_dest_zone",
            "source_ip", "dest_ip", "service",
            "usage_time" (optional),
            "original_policy_id" (optional, 仅用于 audit/log)
        }
        """
        result: Dict[str, Any] = {
            "match_mode": "NEW_RULE",
            "reused_rule_name": None,
            "reused_rule_content": None,
            "push_script": [],
            "audit_message": "",
        }

        req_src_zone = (req.get("device_source_zone") or "any").strip()
        req_dst_zone = (req.get("device_dest_zone") or "any").strip()
        req_src_ip = (req.get("source_ip") or "").strip()
        req_dst_ip = (req.get("dest_ip") or "").strip()
        req_ports = self._split_ports(req.get("service") or "")
        req_time = (req.get("usage_time") or "").strip()

        for rule in self._rules_with_ips:
            rule_name = rule.get("name") or "Unknown"

            # 1. Zone 严格匹配 (任意一侧不一致就过)
            if (rule.get("source_zone") or "any") != req_src_zone:
                continue
            if (rule.get("dest_zone") or "any") != req_dst_zone:
                continue

            # 2. IP 包容 (req 全部 ⊆ exist)
            if not self._ip_is_subset(req_src_ip, rule.get("source_ips") or []):
                continue
            if not self._ip_is_subset(req_dst_ip, rule.get("dest_ips") or []):
                continue

            # 3. Port 包容
            if not self._ports_are_subset(req_ports, rule.get("services") or []):
                continue

            # -------- 4 要素全包容, 进入时间分水岭 --------
            schedule_text = rule.get("schedule_text") or ""
            is_time_covered = self._time_is_subset(req_time, schedule_text)

            result["reused_rule_name"] = rule_name
            result["reused_rule_content"] = self._summarize_rule(rule, schedule_text)

            if is_time_covered:
                # FULL_MATCH: 跳过
                result["match_mode"] = "FULL_MATCH"
                result["push_script"] = []
                result["audit_message"] = (
                    f"完全复用已有策略 [{rule_name}]，各要素均已被包容，本次下发自动跳过。"
                )
                return result
            else:
                # TIME_UPDATE: 修改老策略时间
                result["match_mode"] = "TIME_UPDATE"
                result["push_script"] = self._generate_time_update_cli(
                    rule_name, req_time
                )
                result["audit_message"] = (
                    f"网络资产已落入老策略 [{rule_name}]，但当前需求时间不满足。"
                    f"将通过修改该策略的时间对象进行开通。"
                )
                return result

        # NEW_RULE: 全新建
        result["match_mode"] = "NEW_RULE"
        result["push_script"] = self._generate_full_new_cli(req)
        result["audit_message"] = "未匹配到任何可复用的安全策略，将全新创建策略行。"
        return result

    # ============================================================
    # 子要素比对
    # ============================================================

    @staticmethod
    def _ip_is_subset(req_ip: str, exist_ips: List[str]) -> bool:
        """req_ip ⊆ exist_ips 列表中的任一 IP/CIDR?

        多 IP 字符串 (换行/逗号) 视为集合, **所有** req IP 都要落在 exist 内才算 ✓
        单 IP 只需落在任一 exist 内即可 ✓

        例:
          exist = ["10.0.0.0/8"], req = "10.1.2.3" → True
          exist = ["10.0.0.0/8"], req = "10.1.1.5\n172.16.1.5" → False
          exist = ["any"] → True
        """
        if not req_ip:
            return True
        req_ips = PrePushAnalyzer._split_ips(req_ip)
        if not req_ips:
            return True
        # any 一次性短路
        for ex in exist_ips:
            if ex and ex.lower() == "any":
                return True
        # 每个 req IP 都必须 ⊆ exist 列表中至少一个
        for r in req_ips:
            try:
                r_net = ipaddress.ip_network(r.strip(), strict=False)
            except ValueError:
                continue
            covered = False
            for ex in exist_ips:
                if not ex:
                    continue
                try:
                    ex_net = ipaddress.ip_network(ex.strip(), strict=False)
                except ValueError:
                    continue
                if r_net.subnet_of(ex_net):
                    covered = True
                    break
            if not covered:
                return False  # 有一个不覆盖 → 整体不 ⊆
        return True

    @staticmethod
    def _split_ips(s: str) -> List[str]:
        """拆分多 IP 字符串 (支持换行/逗号/分号/空格)"""
        if not s:
            return []
        parts = re.split(r"[\s,;]+", s.strip())
        return [p for p in parts if p]

    @staticmethod
    def _split_ports(s: str) -> Set[str]:
        """拆分端口, 标准化为集合
        支持: "80", "80 443", "80,443", "80;443", "80-90"
        """
        if not s:
            return set()
        parts = re.split(r"[\s,;]+", s.strip())
        return {p for p in parts if p}

    @staticmethod
    def _ports_are_subset(req_ports: Set[str], exist_services: List[str]) -> bool:
        """req_ports ⊆ exist_services?

        exist_services 是 object name 列表 (H3C), 这里做字符串包含:
          - 'any' 存在 → 全包容
          - 每个 req_port 都要被 exist_services 列表中至少一个 svc 字符串包含 → 算 ⊆
        """
        if not req_ports:
            return True
        if not exist_services:
            return False
        if any(s.lower() == "any" for s in exist_services):
            return True
        exist_lower = [s.lower() for s in exist_services if s]
        for rp in req_ports:
            if not rp:
                continue
            if not any((rp in el) or (el in rp) for el in exist_lower):
                return False
        return True

    @staticmethod
    def _time_is_subset(req_time: str, exist_time_text: str) -> bool:
        """时间包容判断

        exist_time 为空 / 'any' / 等于 req → 包容
        不同 → 不包容
        """
        if not exist_time_text or exist_time_text.strip().lower() in ("any", "always"):
            return True
        if not req_time:
            return True
        return req_time.strip() == exist_time_text.strip()

    # ============================================================
    # CLI 生成
    # ============================================================

    @staticmethod
    def _generate_time_update_cli(rule_name: str, new_time: str) -> List[str]:
        """H3C: 修改老策略的时间对象

        流程:
          1. 新建/更新 time-range 对象 (绝对时间)
          2. 进 security-policy, 切到 rule, 改 time-range
        """
        # 标准化 new_time 为 YYYY-MM-DD (跟 _normalize_valid_until 一致)
        end_date = PrePushAnalyzer._normalize_time(new_time)
        if not end_date:
            end_date = new_time or "长期"
        tr_name = f"TR_UPDATE_{rule_name}"
        # 不指定 start → 立即生效, 到 end_date 23:59:59 截止
        return [
            f"time-range {tr_name} absolute from 00:00:00 2026/01/01 to 23:59:59 {end_date}",
            "security-policy ip",
            f" rule name {rule_name}",
            f" time-range {tr_name}",
            "quit",
        ]

    @staticmethod
    def _normalize_time(raw: str) -> str:
        """YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD → YYYY-MM-DD"""
        if not raw:
            return ""
        raw = raw.strip()
        if raw in ("长期", "always", "any") or not raw:
            return ""
        m = re.match(r"^(\d{4})[\-/.](\d{1,2})[\-/.](\d{1,2})$", raw)
        if m:
            y, mo, d = m.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d}"
        return raw

    @staticmethod
    def _generate_full_new_cli(req: Dict[str, Any]) -> List[str]:
        """H3C: 全新建策略的 CLI 骨架 (与 generate_commands 的逻辑对齐, 但简化)

        实际命令应配合 start-v2 pipeline 走, 这里只给 UI 展示用的脚手架。
        """
        src_ip = req.get("source_ip") or "any"
        dst_ip = req.get("dest_ip") or "any"
        service = req.get("service") or "any"
        return [
            f"# 全新建策略: src={src_ip} dst={dst_ip} svc={service}",
            "security-policy ip",
            f" rule name {req.get('rule_name', 'AUTO_NEW_RULE')}",
            f"  source-zone {req.get('device_source_zone', 'any')}",
            f"  destination-zone {req.get('device_dest_zone', 'any')}",
            f"  source-ip {src_ip}",
            f"  destination-ip {dst_ip}",
            f"  service {service}",
            "  action pass",
            "quit",
        ]


# ============================================================
# 转换工具: H3CClient 解析出的对象 → fw_cache
# ============================================================

def h3c_policies_to_fw_cache(
    addresses: List[Any],       # List[AddressObject] (dataclass)
    services: List[Any],        # List[ServiceObject]
    policies: List[Any],        # List[FirewallPolicy]
    time_ranges: Optional[List[Any]] = None,  # List[ScheduleObject]
) -> Dict[str, Any]:
    """把 H3C 解析出的对象转成 PrePushAnalyzer 用的 fw_cache dict

    字段映射:
      AddressObject: name/value/members
      ServiceObject: name/protocol/dst_port
      FirewallPolicy: name/src_zone/dst_zone/src_addrs/dst_addrs/services/schedule
      ScheduleObject: name/end_date → text
    """
    addr_dicts = [
        {"name": a.name, "value": a.value, "members": a.members}
        for a in addresses
    ]
    # services 在 FirewallPolicy 里是 object name, PrePushAnalyzer 暂时只做字符串包含判断
    # 所以保留 name 即可 (后续需要时再 join protocol+port)
    svc_names = [{"name": s.name, "value": s.dst_port, "members": []} for s in services]

    rule_dicts = [
        {
            "name": p.name,
            "source_zone": p.src_zone,
            "dest_zone": p.dst_zone,
            "src_addrs": p.src_addrs,
            "dst_addrs": p.dst_addrs,
            "services": p.services,
            "schedule": p.schedule,
        }
        for p in policies
        if getattr(p, "enabled", True) and getattr(p, "action", "accept") == "accept"
    ]

    time_dicts = []
    if time_ranges:
        for t in time_ranges:
            if t.end_date:
                text = f"absolute to {t.end_date}"
            else:
                text = t.schedule_type
            time_dicts.append({"name": t.name, "text": text})

    return {
        "rules": rule_dicts,
        "addresses": addr_dicts + svc_names,
        "time_ranges": time_dicts,
    }
