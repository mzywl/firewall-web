"""H3C 防火墙客户端

参照旧版 /home/lishiyu/output/lishiyu/cx/H3C防火墙策略.py 重构:
- 拉配置: dis cur (GB2312 编码)
- 地址对象: object-group ip address "..."
- 服务对象: object-group service "TCP-..." / "UDP-..."
- 策略: rule name "..." / security-policy ip
- 时间: time-range "..."

注意: 这是简化版骨架，完整规则解析留给后续 PR 扩充。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .base import (
    AddressObject,
    ConnectionTestResult,
    FirewallClient,
    FirewallPolicy,
    ServiceObject,
)


class H3CClient(FirewallClient):
    """H3C 防火墙客户端"""

    @property
    def encoding(self) -> str:
        return "gb2312"

    # ---------- 版本/连接 ----------

    def _read_version(self) -> str:
        """display version | include H3C"""
        self.shell.send(self.encode("display version | include H3C\n"))
        return self._recv_until("[H3C]", idle_pause=0.5, max_wait=5)

    def _config_command(self) -> Tuple[str, str]:
        """dis cur + 终止标记 return"""
        return "dis cur", "return"

    # ---------- 解析 ----------

    def parse_config(
        self, config_text: str
    ) -> Tuple[List[AddressObject], List[ServiceObject], List[FirewallPolicy]]:
        """解析 H3C 配置文本

        完整解析需要非常多的正则（旧版 cx/H3C防火墙策略.py 有 800+ 行）。
        这里只做骨架：识别 object-group 和 security-policy 段。
        """
        addresses = self._parse_addresses(config_text)
        services = self._parse_services(config_text)
        policies = self._parse_policies(config_text, addresses, services)
        return addresses, services, policies

    def _parse_addresses(self, text: str) -> List[AddressObject]:
        """解析 object-group ip address 段"""
        result = []
        # 匹配一个 object-group 块: object-group ip address "name"\n ... \n
        pattern = re.compile(
            r'object-group\s+ip\s+address\s+"([^"]+)"\s*\n(.*?)(?=^object-group\s+ip\s+address\s+"|^quit\s*$)',
            re.M | re.S,
        )
        for m in pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            # body 含 network host/subnet/range
            members = []
            for line in body.split("\n"):
                line = line.strip()
                if "network host address" in line:
                    val = line.split()[-1]
                    members.append(val)
                elif "network subnet" in line:
                    parts = line.split()
                    val = f"{parts[-2]}/{parts[-1]}"
                    members.append(val)
                elif "network range" in line:
                    parts = line.split()
                    val = f"{parts[-2]}-{parts[-1]}"
                    members.append(val)
                elif "network group-object" in line:
                    members.append(f"@{line.split()[-1]}")
            if members:
                result.append(AddressObject(
                    name=name, type="group", value="", members=members,
                ))
        return result

    def _parse_services(self, text: str) -> List[ServiceObject]:
        """解析 object-group service 段"""
        result = []
        pattern = re.compile(
            r'object-group\s+service\s+"(TCP-[^"]+|UDP-[^"]+)"\s*\n(.*?)(?=^object-group\s+service\s+"|^quit\s*$)',
            re.M | re.S,
        )
        for m in pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            proto = "tcp" if name.startswith("TCP-") else "udp"
            port = name.split("-", 1)[1]
            result.append(ServiceObject(
                name=name, protocol=proto, dst_port=port, members=[],
            ))
        return result

    def _parse_policies(
        self, text: str,
        addresses: List[AddressObject],
        services: List[ServiceObject],
    ) -> List[FirewallPolicy]:
        """解析 security-policy ip 段下的 rule"""
        result = []
        # 找 security-policy ip 段
        sec_match = re.search(
            r"security-policy\s+ip\s*\n(.*?)(?=^return\s*$|\Z)", text, re.M | re.S,
        )
        if not sec_match:
            return result
        body = sec_match.group(1)
        # 每个 rule 是 rule name "X"\n ... \n
        rule_pat = re.compile(
            r'rule\s+name\s+"([^"]+)"\s*\n(.*?)(?=^rule\s+name\s+"|^quit\s*$)',
            re.M | re.S,
        )
        for m in rule_pat.finditer(body):
            name = m.group(1)
            rb = m.group(2)
            src_zone = self._extract_field(rb, "source-zone") or "any"
            dst_zone = self._extract_field(rb, "destination-zone") or "any"
            src_addrs = re.findall(r'source-ip\s+"?([^"\s]+)"?', rb)
            dst_addrs = re.findall(r'destination-ip\s+"?([^"\s]+)"?', rb)
            svcs = re.findall(r'service\s+"?([^"\s]+)"?', rb)
            sched = self._extract_field(rb, "time-range")
            action = "deny"
            if "action pass" in rb or "action permit" in rb:
                action = "accept"
            enabled = "disable" not in rb
            result.append(FirewallPolicy(
                policy_id=name, name=name,
                src_zone=src_zone, dst_zone=dst_zone,
                src_addrs=src_addrs, dst_addrs=dst_addrs,
                services=svcs, schedule=sched,
                action=action, enabled=enabled,
            ))
        return result

    def _extract_field(self, text: str, key: str) -> str:
        m = re.search(rf'^{key}\s+"?([^"\s]+)"?', text, re.M)
        return m.group(1) if m else ""

    # ---------- 命令生成 ----------

    def generate_commands(
        self,
        new_policies: List[Dict[str, Any]],
        existing_addresses: List[AddressObject],
        existing_services: List[ServiceObject],
        existing_schedules: List,
    ) -> List[str]:
        """生成 H3C 的 CLI 命令

        new_policies 每条是 dict:
            {
                "src_ips": ["10.1.1.0/24", "10.2.2.1", ...],
                "dst_ips": [...],
                "ports": ["80", "443", "UDP:53"],
                "valid_until": "2025-12-31" 或 "长期",
                "src_zone": "trust",
                "dst_zone": "untrust",
                "rule_name": "工单号-源-目的",
            }
        """
        cmds: List[str] = []
        # 进入配置模式
        cmds.append("system-view")
        # 先建缺的地址对象 + 服务对象
        for p in new_policies:
            cmds.extend(self._gen_address_objects(
                p["src_ips"], f"{p['rule_name']}-src", existing_addresses,
            ))
            cmds.extend(self._gen_address_objects(
                p["dst_ips"], f"{p['rule_name']}-dst", existing_addresses,
            ))
            cmds.extend(self._gen_service_objects(
                p["ports"], f"{p['rule_name']}-svc", existing_services,
            ))
        # time-range 跨规则 dedup — 同日期只建一次 (用日期作为 name, H3C 实际命令格式)
        seen_schedules = set()
        for p in new_policies:
            vu = p.get("valid_until", "")
            if vu and "长期" not in vu and vu not in seen_schedules:
                seen_schedules.add(vu)
                cmds.extend(self._gen_schedule_object(vu))
        # 然后建策略
        cmds.append("security-policy ip")
        for p in new_policies:
            # 每条策略可能多行命令（rule name + 各属性 + action）
            cmds.extend(self._gen_rule_command(p))
        cmds.append("quit")
        # 退 system-view (H3C 用 return 跟 quit 等价, 跟用户示例一致)
        cmds.append("return")
        # 保存配置 (H3C 推送必须 save force, 否则重启后丢)
        cmds.append("save force")
        return cmds

    def _gen_address_objects(
        self, ips: List[str], name_prefix: str, existing: List[AddressObject]
    ) -> List[str]:
        """生成地址对象创建命令，复用已存在的

        对象名: 纯 IP 形式 (跟 H3C 真实命令一致)
          - 单 IP: 10.2.179.130
          - 范围: 192.169.1.135-142 (短格式, 同 /24 范围内只写末尾)
          - 子网: 10.2.179.0/24
        H3C object name 允许纯 IP (无前缀无引号), 不用 addr- 前缀
        (Sangfor 必须保留 addr- 前缀 — 设备 object name 约束, 字母开头)
        """
        existing_values = {a.value: a.name for a in existing if a.value}
        new_addrs = []
        for ip in ips:
            if ip in existing_values:
                continue
            new_addrs.append(ip)
        if not new_addrs:
            return []
        cmds = []
        for ip in new_addrs:
            if "/" in ip:
                net, mask = ip.split("/")
                cmds.append(f"object-group ip address {ip}")
                cmds.append(f"network subnet {net} {self._mask_from_prefix(int(mask))}")
                cmds.append("quit")
            elif "-" in ip:
                # 范围 IP: 短格式 (同 /24 范围只写末尾 octet)
                a, b = ip.split("-", 1)
                a_parts = a.split(".")
                b_parts = b.split(".") if "." in b else None
                if b_parts and a_parts[:3] == b_parts[:3]:
                    # 同 /24 范围内: 192.169.1.135-142
                    short_ip = f"{a}-{b_parts[3]}"
                else:
                    short_ip = ip
                cmds.append(f"object-group ip address {short_ip}")
                cmds.append(f"network range {a} {b}")
                cmds.append("quit")
            else:
                cmds.append(f"object-group ip address {ip}")
                cmds.append(f"network host address {ip}")
                cmds.append("quit")
        return cmds

    def _gen_service_objects(
        self, ports: List[str], name_prefix: str, existing: List[ServiceObject]
    ) -> List[str]:
        existing_keys = {(s.protocol, s.dst_port): s.name for s in existing}
        new_ports = [p for p in ports if self._port_key(p) not in existing_keys]
        if not new_ports:
            return []
        cmds = []
        for p in new_ports:
            if p.startswith("UDP:"):
                port = p.split(":")[1]
                obj_name = f"UDP-{port}"
                if "-" in port:
                    a, b = port.split("-")
                    cmds.append(f"object-group service {obj_name}")
                    cmds.append(f"service udp destination range {a} {b}")
                else:
                    cmds.append(f"object-group service {obj_name}")
                    cmds.append(f"service udp destination eq {port}")
                cmds.append("quit")
            else:
                port = p
                obj_name = f"TCP-{port}"
                if "-" in port:
                    a, b = port.split("-")
                    cmds.append(f"object-group service {obj_name}")
                    cmds.append(f"service tcp destination range {a} {b}")
                else:
                    cmds.append(f"object-group service {obj_name}")
                    cmds.append(f"service tcp destination eq {port}")
                cmds.append("quit")
        return cmds

    def _gen_schedule_object(self, valid_until: str) -> List[str]:
        """生成 H3C time-range 命令

        命名: 用日期作为 name (例: `time-range 2026-12-31 ...`)
              不再用 `{rule_name}-sched` — 跨规则共享同一日期时 dedup 共用
        日期格式: MM/DD/YYYY (美式, 跟 H3C 真实命令一致)
        """
        if not valid_until or "长期" in valid_until:
            return []
        # valid_until 格式: "2025-12-31" → 转 "12/31/2025"
        try:
            from datetime import datetime
            date_obj = datetime.strptime(valid_until.replace("/", "-"), "%Y-%m-%d")
            us_date = date_obj.strftime("%m/%d/%Y")
            start_date = "01/01/2026"  # 跟用户示例一致: 从 2026-01-01 开始
        except ValueError:
            # 解析失败兜底
            us_date = valid_until.replace("-", "/")
            start_date = "01/01/2021"
        cmds = [
            f"time-range {valid_until} from 00:00:01 {start_date} to 23:59:59 {us_date}",
        ]
        return cmds

    def _gen_rule_command(self, p: Dict[str, Any]) -> List[str]:
        """生成 H3C 单条 rule 的完整命令（多行）

        H3C 真实命令顺序:
          rule name "..."
          action pass
          counting enable
          logging enable
          source-zone / destination-zone
          source-ip / destination-ip (引用 addr-{ip})
          service (引用 TCP-X / UDP-X)
          time-range (引用时间对象名)

        object name 跨 src/dst 复用 — 同 IP 只建一个, rule 引用纯 IP 形式
        """
        cmds = [f'rule name "{p["rule_name"]}"']
        # 动作 (H3C 习惯 action 在前)
        action = p.get("action", "permit")
        cmds.append(f"action {action if action in ('permit', 'deny') else 'pass'}")
        # 流量统计 + 日志 (H3C 推荐启用)
        cmds.append("counting enable")
        cmds.append("logging enable")
        # 区域
        if p.get("src_zone") and p["src_zone"] != "any":
            cmds.append(f"source-zone {p['src_zone']}")
        if p.get("dst_zone") and p["dst_zone"] != "any":
            cmds.append(f"destination-zone {p['dst_zone']}")
        # 源 IP
        for ip in p.get("src_ips", []):
            cmds.append(f'source-ip "{ip}"')
        # 目的 IP
        for ip in p.get("dst_ips", []):
            cmds.append(f'destination-ip "{ip}"')
        # 服务
        for port in p.get("ports", []):
            if port.startswith("UDP:"):
                port_v = port.split(":", 1)[1]
                cmds.append(f'service "UDP-{port_v}"')
            else:
                cmds.append(f'service "TCP-{port}"')
        # 时间
        vu = p.get("valid_until", "")
        if vu and "长期" not in vu:
            cmds.append(f"time-range {vu}")
        return cmds

    def _port_key(self, p: str) -> tuple:
        if p.startswith("UDP:"):
            return ("udp", p.split(":", 1)[1])
        return ("tcp", p)

    def _mask_from_prefix(self, prefix: int) -> str:
        """从 /24 算出 255.255.255.0"""
        bits = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        return f"{(bits >> 24) & 0xFF}.{(bits >> 16) & 0xFF}.{(bits >> 8) & 0xFF}.{bits & 0xFF}"

    # ---------- 推送 ----------

    def _push_preamble(self) -> str:
        return "system-view"

    def _push_postamble(self) -> str:
        return "save\ny"  # H3C 配置完通常要 save

    def _is_fatal_error(self, error: str) -> bool:
        # H3C 错误信息 % 是致命的
        return "% " in error
