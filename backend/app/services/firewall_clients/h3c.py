from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Tuple, Set

from .base import (
    AddressObject,
    ConnectionTestResult,
    FirewallClient,
    FirewallPolicy,
    ServiceObject,
)


class H3CClient(FirewallClient):
    """H3C 防火墙客户端优化版（已修复跨策略去重 Bug）"""

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
        """解析 H3C 配置文本"""
        addresses = self._parse_addresses(config_text)
        services = self._parse_services(config_text)
        policies = self._parse_policies(config_text, addresses, services)
        return addresses, services, policies

    def _parse_addresses(self, text: str) -> List[AddressObject]:
        """解析 object-group ip address 段"""
        result = []
        pattern = re.compile(
            r'object-group\s+ip\s+address\s+"([^"]+)"\s*\n(.*?)(?=^\s*object-group\s+ip\s+address\s+"|^\s*quit\s*$)',
            re.M | re.S,
        )
        for m in pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            members = []
            for line in body.split("\n"):
                line = line.strip()
                if "network host address" in line:
                    members.append(line.split()[-1])
                elif "network subnet" in line:
                    parts = line.split()
                    members.append(f"{parts[-2]}/{parts[-1]}")
                elif "network range" in line:
                    parts = line.split()
                    members.append(f"{parts[-2]}-{parts[-1]}")
                elif "network group-object" in line:
                    members.append(f"@{line.split()[-1]}")
            if members:
                result.append(AddressObject(
                    name=name, type="group", value=name, members=members,
                ))
        return result

    def _parse_services(self, text: str) -> List[ServiceObject]:
        """解析 object-group service 段"""
        result = []
        pattern = re.compile(
            r'object-group\s+service\s+"(TCP-[^"]+|UDP-[^"]+)"\s*\n(.*?)(?=^\s*object-group\s+service\s+"|^\s*quit\s*$)',
            re.M | re.S,
        )
        for m in pattern.finditer(text):
            name = m.group(1)
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
        sec_match = re.search(
            r"security-policy\s+ip\s*\n(.*?)(?=^\s*return\s*$|\Z)", text, re.M | re.S,
        )
        if not sec_match:
            return result

        body = sec_match.group(1)
        rule_pat = re.compile(
            r'rule\s+name\s+"([^"]+)"\s*\n(.*?)(?=^\s*rule\s+name\s+"|^\s*quit\s*$)',
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

            action = "accept" if "action pass" in rb or "action permit" in rb else "deny"
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
        m = re.search(rf'^\s*{key}\s+"?([^"\s]+)"?', text, re.M)
        return m.group(1) if m else ""

    # ---------- 命令生成 ----------

    def generate_commands(
            self,
            new_policies: List[Dict[str, Any]],
            existing_addresses: List[AddressObject],
            existing_services: List[ServiceObject],
            existing_schedules: List[Any],
    ) -> List[str]:
        """生成 H3C 的 CLI 命令"""
        cmds: List[str] = ["system-view"]

        # 1. 汇总所有策略中的 IP 和 端口，进行全局去重
        all_ips: Set[str] = set()
        all_ports: Set[str] = set()
        for p in new_policies:
            all_ips.update(p.get("src_ips", []))
            all_ips.update(p.get("dst_ips", []))
            all_ports.update(p.get("ports", []))

        # 2. 统一批量生成缺少的地址与服务对象（全局只需调用一次）
        cmds.extend(self._gen_address_objects(list(all_ips), existing_addresses))
        cmds.extend(self._gen_service_objects(list(all_ports), existing_services))

        # 3. time-range 跨规则去重生成
        seen_schedules: Set[str] = set()
        for p in new_policies:
            vu = p.get("valid_until", "")
            if vu and "长期" not in vu and vu not in seen_schedules:
                seen_schedules.add(vu)
                cmds.extend(self._gen_schedule_object(vu))

        # 4. 生成安全策略
        cmds.append("security-policy ip")
        for p in new_policies:
            cmds.extend(self._gen_rule_command(p))

        cmds.extend(["quit", "return", "save force"])
        return cmds

    def _get_addr_obj_name(self, ip: str) -> str:
        """获取标准的 H3C 地址对象名称（支持同/24网段范围缩减）"""
        if "-" in ip:
            a, b = ip.split("-", 1)
            a_parts, b_parts = a.split("."), b.split(".")
            if len(a_parts) == 4 and len(b_parts) == 4 and a_parts[:3] == b_parts[:3]:
                return f"{a}-{b_parts[3]}"
        return ip

    def _gen_address_objects(self, ips: List[str], existing: List[AddressObject]) -> List[str]:
        """生成地址对象创建命令"""
        existing_names = {a.name for a in existing}
        cmds = []

        for ip in ips:
            obj_name = self._get_addr_obj_name(ip)
            if obj_name in existing_names:
                continue

            cmds.append(f"object-group ip address {obj_name}")
            if "/" in ip:
                net, mask = ip.split("/")
                cmds.append(f"network subnet {net} {self._mask_from_prefix(int(mask))}")
            elif "-" in ip:
                a, b = ip.split("-", 1)
                cmds.append(f"network range {a} {b}")
            else:
                cmds.append(f"network host address {ip}")
            cmds.append("quit")

            existing_names.add(obj_name)
        return cmds

    def _gen_service_objects(self, ports: List[str], existing: List[ServiceObject]) -> List[str]:
        """生成服务对象"""
        existing_keys = {(s.protocol, s.dst_port) for s in existing}
        cmds = []

        for p in ports:
            proto, port = ("udp", p.split(":", 1)[1]) if p.startswith("UDP:") else ("tcp", p)
            if (proto, port) in existing_keys:
                continue

            obj_name = f"{proto.upper()}-{port}"
            cmds.append(f"object-group service {obj_name}")

            op = "range" if "-" in port else "eq"
            val = port.replace("-", " ")
            cmds.append(f"service {proto} destination {op} {val}")
            cmds.append("quit")

            existing_keys.add((proto, port))
        return cmds

    def _gen_schedule_object(self, valid_until: str) -> List[str]:
        """生成 H3C time-range 命令"""
        if not valid_until or "长期" in valid_until:
            return []
        try:
            date_obj = datetime.strptime(valid_until.replace("/", "-"), "%Y-%m-%d")
            us_date = date_obj.strftime("%m/%d/%Y")
        except ValueError:
            us_date = valid_until.replace("-", "/")

        start_date = f"01/01/{datetime.now().year}"
        return [f"time-range {valid_until} from 00:00:01 {start_date} to 23:59:59 {us_date}"]

    def _gen_rule_command(self, p: Dict[str, Any]) -> List[str]:
        """生成单条安全策略规则"""
        cmds = [f'rule name "{p["rule_name"]}"']

        action = p.get("action", "permit")
        # 兼容 H3C 常用动作关键字表达方式
        cmds.append(f"action {action if action in ('deny', 'pass', 'drop') else 'pass'}")
        cmds.extend(["counting enable", "logging enable"])

        if p.get("src_zone") and p["src_zone"] != "any":
            cmds.append(f"source-zone {p['src_zone']}")
        if p.get("dst_zone") and p["dst_zone"] != "any":
            cmds.append(f"destination-zone {p['dst_zone']}")

        for ip in p.get("src_ips", []):
            cmds.append(f'source-ip "{self._get_addr_obj_name(ip)}"')
        for ip in p.get("dst_ips", []):
            cmds.append(f'destination-ip "{self._get_addr_obj_name(ip)}"')

        for port in p.get("ports", []):
            proto, port_v = ("UDP", port.split(":", 1)[1]) if port.startswith("UDP:") else ("TCP", port)
            cmds.append(f'service "{proto}-{port_v}"')

        vu = p.get("valid_until", "")
        if vu and "长期" not in vu:
            cmds.append(f"time-range {vu}")
        return cmds

    def _mask_from_prefix(self, prefix: int) -> str:
        """从前缀长度计算掩码（例：24 -> 255.255.255.0）"""
        bits = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        return f"{(bits >> 24) & 0xFF}.{(bits >> 16) & 0xFF}.{(bits >> 8) & 0xFF}.{bits & 0xFF}"

    # ---------- 推送 ----------

    def _push_preamble(self) -> str:
        return "system-view"

    def _push_postamble(self) -> str:
        return "save\ny"

    def _is_fatal_error(self, error: str) -> bool:
        return "% " in error