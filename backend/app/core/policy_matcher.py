"""策略匹配器

两种模式:
- deduplicate (查重): 复用整条 + 复用对象
- force_push   (全推): 不复用整条（必新建），但对象层仍复用

匹配维度: src_ips, dst_ips, ports, valid_until (4 个)
复用单位: 整条策略 / 地址对象 / 服务对象 / 时间对象
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.firewall_clients.base import (
    AddressObject,
    FirewallPolicy,
    ScheduleObject,
    ServiceObject,
)


class MatchAction(str, Enum):
    """匹配后的动作"""
    REUSED = "reused"           # 整条复用（仅 deduplicate 模式）
    APPENDED = "appended"       # 追加（仅 deduplicate 模式）
    CREATED = "created"         # 新建（force_push 模式 + 查重未命中）
    FAILED = "failed"


@dataclass
class ObjectReuse:
    """复用的对象（src/dst/svc/sched）"""
    src_addrs: List[str] = field(default_factory=list)   # 复用的设备对象名
    dst_addrs: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    schedule: Optional[str] = None
    new_src_addrs: List[str] = field(default_factory=list)  # 需要新建的
    new_dst_addrs: List[str] = field(default_factory=list)
    new_services: List[str] = field(default_factory=list)
    new_schedule: bool = False


@dataclass
class MatchResult:
    """单条工单策略的匹配结果"""
    policy_id: Optional[int] = None        # 工单 Policy 表 ID
    action: MatchAction = MatchAction.CREATED
    match_key: str = ""                    # 4 维度 hash（用于去重 + 审计）
    existing_device_policy_id: Optional[str] = None  # 设备上已存在策略的 ID
    reuse: ObjectReuse = field(default_factory=ObjectReuse)
    diff: Dict[str, Any] = field(default_factory=dict)  # 差集（仅 partial 时有值）
    error: str = ""


class PolicyMatcher:
    """策略匹配器"""

    def __init__(
        self,
        mode: str,
        existing_addresses: List[AddressObject],
        existing_services: List[ServiceObject],
        existing_schedules: List[ScheduleObject],
        existing_policies: List[FirewallPolicy],
    ):
        self.mode = mode  # "deduplicate" / "force_push"
        self.existing_addresses = existing_addresses
        self.existing_services = existing_services
        self.existing_schedules = existing_schedules
        self.existing_policies = existing_policies

        # 建索引: value -> name（精确匹配）
        self.addr_index: Dict[str, str] = {a.value: a.name for a in existing_addresses if a.value}
        # 反向索引: name -> value（用于把设备上的对象名解析成实际 IP）
        self.addr_name_to_value: Dict[str, str] = {
            a.name: a.value for a in existing_addresses if a.name and a.value
        }
        self.svc_index: Dict[Tuple[str, str], str] = {
            (s.protocol, s.dst_port): s.name for s in existing_services
        }
        self.sched_index: Dict[str, str] = {
            self._norm_schedule(s.end_date): s.name for s in existing_schedules if s.end_date
        }

    # ============================================================
    # 公开 API
    # ============================================================

    def match_one(
        self,
        src_ips: List[str],
        dst_ips: List[str],
        ports: List[str],
        valid_until: str,
        rule_name: str = "",
        policy_id: Optional[int] = None,
        src_zone: str = "any",
        dst_zone: str = "any",
        translated_src_ips: Optional[List[str]] = None,
        translated_dst_ips: Optional[List[str]] = None,
    ) -> MatchResult:
        """匹配一条工单策略

        translated_*_ips: 同 region 内前序边界墙 SNAT 后的 IP（NAT 透传）
                         非 None 时用于替换 hash 和精确比对的 IP
        """
        # 实际参与匹配的 IP：优先用 translated
        effective_src = translated_src_ips if translated_src_ips is not None else src_ips
        effective_dst = translated_dst_ips if translated_dst_ips is not None else dst_ips

        match_key = self._compute_match_key(effective_src, effective_dst, ports, valid_until)
        reuse = self._resolve_object_reuse(effective_src, effective_dst, ports, valid_until)

        # 1) deduplicate 模式：先查整条策略
        if self.mode == "deduplicate":
            hit = self._find_exact_policy(effective_src, effective_dst, ports, valid_until, src_zone, dst_zone)
            if hit:
                return MatchResult(
                    policy_id=policy_id,
                    action=MatchAction.REUSED,
                    match_key=match_key,
                    existing_device_policy_id=hit.policy_id,
                    reuse=reuse,
                )

        # 2) 走到这里: 必新建
        return MatchResult(
            policy_id=policy_id,
            action=MatchAction.CREATED,
            match_key=match_key,
            reuse=reuse,
        )

    # ============================================================
    # 内部：整条策略查重
    # ============================================================

    def _find_exact_policy(
        self,
        src_ips: List[str],
        dst_ips: List[str],
        ports: List[str],
        valid_until: str,
        src_zone: str,
        dst_zone: str,
    ) -> Optional[FirewallPolicy]:
        """在设备已有策略里找 4 维度 + zone 都完全匹配的

        关键：把设备上的对象名（p.src_addrs）解析成实际 IP，再跟工单 IP 比
        关键：把设备上的服务名（"TCP-80"）剥成裸端口（"80"）再比
        """
        src_set = set(self._norm_ip_list(src_ips))
        dst_set = set(self._norm_ip_list(dst_ips))
        port_set = set(self._norm_port_list(ports))
        sched_norm = self._norm_schedule(valid_until)

        for p in self.existing_policies:
            if not p.enabled:
                continue
            if p.action != "accept":
                continue
            # zone
            if src_zone and p.src_zone != src_zone and p.src_zone != "any":
                continue
            if dst_zone and p.dst_zone != dst_zone and p.dst_zone != "any":
                continue
            # 把设备上的对象名 → 实际 IP
            p_src_ips = self._resolve_obj_names_to_ips(p.src_addrs)
            p_dst_ips = self._resolve_obj_names_to_ips(p.dst_addrs)
            if set(p_src_ips) != src_set:
                continue
            if set(p_dst_ips) != dst_set:
                continue
            # 端口：把 "TCP-80" / "UDP-53" 剥成 "80" / "53"
            p_ports = self._strip_service_prefix(p.services)
            if set(p_ports) != port_set:
                continue
            p_sched = self._norm_schedule(p.schedule)
            if p_sched != sched_norm:
                continue
            return p
        return None

    @staticmethod
    def _strip_service_prefix(svc_names: List[str]) -> List[str]:
        """把 ['TCP-80', 'UDP-53'] → ['80', '53']，未知原样保留"""
        result = []
        for s in svc_names:
            s = s.strip()
            if s.startswith("TCP-"):
                result.append(s[4:])
            elif s.startswith("UDP-"):
                result.append(s[4:])
            else:
                result.append(s)
        return result

    def _resolve_obj_names_to_ips(self, names: List[str]) -> List[str]:
        """把设备上的对象名列表解析成实际 IP 列表

        已知是对象名（不在工单 IP 集合）→ 查 addr_name_to_value
        未知（可能是 "any" / 内置名）→ 原样保留
        """
        result = []
        for n in names:
            if n in self.addr_name_to_value:
                result.append(self.addr_name_to_value[n])
            else:
                # 不是已知对象名（可能 "any" / "0.0.0.0/0" / 未解析）→ 标准化后保留
                result.append(self._norm_ip(n))
        return result

    # ============================================================
    # 内部：对象复用解析
    # ============================================================

    def _resolve_object_reuse(
        self,
        src_ips: List[str],
        dst_ips: List[str],
        ports: List[str],
        valid_until: str,
    ) -> ObjectReuse:
        """对每个 IP/端口/时间，查询是否已有对象可复用"""
        reuse = ObjectReuse()

        for ip in self._norm_ip_list(src_ips):
            if ip in self.addr_index:
                reuse.src_addrs.append(self.addr_index[ip])
            else:
                reuse.new_src_addrs.append(ip)
        for ip in self._norm_ip_list(dst_ips):
            if ip in self.addr_index:
                reuse.dst_addrs.append(self.addr_index[ip])
            else:
                reuse.new_dst_addrs.append(ip)

        for port in self._norm_port_list(ports):
            key = self._port_key(port)
            if key in self.svc_index:
                reuse.services.append(self.svc_index[key])
            else:
                reuse.new_services.append(port)

        sched_norm = self._norm_schedule(valid_until)
        if sched_norm in self.sched_index:
            reuse.schedule = self.sched_index[sched_norm]
        elif sched_norm and sched_norm != "always":
            reuse.new_schedule = True

        return reuse

    # ============================================================
    # 工具方法
    # ============================================================

    @staticmethod
    def _compute_match_key(
        src_ips: List[str],
        dst_ips: List[str],
        ports: List[str],
        valid_until: str,
    ) -> str:
        """计算 4 维度的 hash（用于去重 + 审计）"""
        s_src = ",".join(sorted(set(PolicyMatcher._norm_ip_list(src_ips))))
        s_dst = ",".join(sorted(set(PolicyMatcher._norm_ip_list(dst_ips))))
        s_port = ",".join(sorted(set(PolicyMatcher._norm_port_list(ports))))
        s_sched = PolicyMatcher._norm_schedule(valid_until)
        raw = f"{s_src}|{s_dst}|{s_port}|{s_sched}"
        return hashlib.sha1(raw.encode()).hexdigest()[:30]

    @staticmethod
    def _norm_ip(ip: str) -> str:
        """标准化 IP: 10.1.1 → 10.1.1.0/32（小段转 /32）"""
        ip = ip.strip()
        if "/" in ip or "-" in ip:
            return ip
        # 单 IP 加 /32
        if ip.count(".") == 3:
            return f"{ip}/32"
        return ip

    @staticmethod
    def _norm_ip_list(ips: List[str]) -> List[str]:
        return [PolicyMatcher._norm_ip(i) for i in ips if i]

    @staticmethod
    def _norm_port(port: str) -> str:
        return port.strip()

    @staticmethod
    def _norm_port_list(ports: List[str]) -> List[str]:
        return [PolicyMatcher._norm_port(p) for p in ports if p]

    @staticmethod
    def _norm_schedule(s) -> str:
        if s is None:
            return "always"
        s = str(s).strip()
        if not s or "长期" in s or s.lower() in ("always", "none", "nan"):
            return "always"
        # 标准化日期格式
        return s.replace("/", "-")

    @staticmethod
    def _port_key(port: str) -> Tuple[str, str]:
        """(proto, port_v) 键"""
        if port.startswith("UDP:"):
            return ("udp", port.split(":", 1)[1])
        return ("tcp", port)
