"""飞塔 (Fortigate) 防火墙客户端

参照旧版 /home/lishiyu/output/lishiyu/cx/飞塔防火墙策略.py
- 拉配置: show full-configuration
- 地址: edit "..." set type ipmask/iprange/fqdn set subnet/range/fqdn
- 服务: edit "TCP-..." set protocol ... set tcp-portrange/udp-portrange
- 策略: edit <id> set srcintf ... set srcaddr ... set dstintf ... set dstaddr ... set action accept set schedule ... set service ... set logtraffic enable
- 段头: define firewall address / define firewall addrgrp / define firewall service custom / define firewall service group / define firewall policy
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .base import (
    AddressObject,
    FirewallClient,
    FirewallPolicy,
    ServiceObject,
)


class FortigateClient(FirewallClient):

    def _read_version(self) -> str:
        self.shell.send(self.encode("get system status\n"))
        return self._recv_until("#", idle_pause=0.5, max_wait=5)

    def _config_command(self) -> Tuple[str, str]:
        return "show full-configuration", "config router multicast"

    def parse_config(
        self, config_text: str
    ) -> Tuple[List[AddressObject], List[ServiceObject], List[FirewallPolicy]]:
        """简化版解析。完整版需要 parse_fortigate_full 函数（旧版 700+ 行）"""
        addresses = self._parse_fortigate_addresses(config_text)
        services = self._parse_fortigate_services(config_text)
        policies = self._parse_fortigate_policies(config_text)
        return addresses, services, policies

    def _parse_fortigate_addresses(self, text: str) -> List[AddressObject]:
        """define firewall address 段下的 edit "..." set type ... set subnet/range/..."""
        result = []
        # 简化: 只识别 subnet
        pattern = re.compile(
            r'edit\s+"([^"]+)"\s*\nset\s+type\s+ipmask\s*\nset\s+subnet\s+([\d./]+)',
        )
        for m in pattern.finditer(text):
            result.append(AddressObject(
                name=m.group(1), type="subnet", value=m.group(2),
            ))
        return result

    def _parse_fortigate_services(self, text: str) -> List[ServiceObject]:
        result = []
        pattern = re.compile(
            r'edit\s+"(TCP-[^"]+|UDP-[^"]+)"\s*\nset\s+protocol\s+TCP/UDP/SCTP\s*\nset\s+(tcp|udp)-portrange\s+([\d-]+)',
        )
        for m in pattern.finditer(text):
            proto = m.group(2)
            port = m.group(3)
            result.append(ServiceObject(
                name=m.group(1), protocol=proto, dst_port=port,
            ))
        return result

    def _parse_fortigate_policies(self, text: str) -> List[FirewallPolicy]:
        result = []
        # 简化: 只抓 edit <id> ... set action accept ... 段
        pattern = re.compile(
            r'edit\s+(\d+)\s*\nset\s+srcintf\s+"?([^"\n]+)"?\s*\nset\s+dstintf\s+"?([^"\n]+)"?\s*\n'
            r'set\s+srcaddr\s+"?([^"\n]+)"?\s*\nset\s+dstaddr\s+"?([^"\n]+)"?\s*\n'
            r'set\s+action\s+(\w+)\s*\nset\s+schedule\s+"?([^"\n]*)"?\s*\n'
            r'set\s+service\s+"?([^"\n]+)"?',
        )
        for m in pattern.finditer(text):
            pid = m.group(1)
            result.append(FirewallPolicy(
                policy_id=pid, name=f"policy-{pid}",
                src_zone=m.group(2), dst_zone=m.group(3),
                src_addrs=m.group(4).split(), dst_addrs=m.group(5).split(),
                services=m.group(8).split(), schedule=m.group(7) or None,
                action="accept" if "accept" in m.group(6) else "deny",
                enabled=True,
            ))
        return result

    def generate_commands(
        self,
        new_policies: List[Dict[str, Any]],
        existing_addresses: List[AddressObject],
        existing_services: List[ServiceObject],
        existing_schedules: List,
    ) -> List[str]:
        cmds: List[str] = []
        # 飞塔的推送是 define ... end 块
        addr_block = self._build_fortigate_address_block(new_policies, existing_addresses)
        addrgrp_block = self._build_fortigate_addrgrp_block(new_policies, existing_addresses)
        svc_block = self._build_fortigate_service_block(new_policies, existing_services)
        svcgrp_block = self._build_fortigate_service_group_block(new_policies)
        sched_block = self._build_fortigate_schedule_block(new_policies, existing_schedules)
        policy_block = self._build_fortigate_policy_block(new_policies)

        if addr_block:
            cmds.append("config firewall address")
            cmds.extend(addr_block)
            cmds.append("end")
        if addrgrp_block:
            cmds.append("config firewall addrgrp")
            cmds.extend(addrgrp_block)
            cmds.append("end")
        if svc_block:
            cmds.append("config firewall service custom")
            cmds.extend(svc_block)
            cmds.append("end")
        if svcgrp_block:
            cmds.append("config firewall service group")
            cmds.extend(svcgrp_block)
            cmds.append("end")
        if sched_block:
            cmds.append("config firewall schedule onetime")
            cmds.extend(sched_block)
            cmds.append("end")
        if policy_block:
            cmds.append("config firewall policy")
            cmds.extend(policy_block)
            cmds.append("end")
        return cmds

    def _build_fortigate_address_block(self, policies, existing):
        existing_values = {a.value: a.name for a in existing if a.value}
        cmds = []
        for p in policies:
            for ip in p["src_ips"] + p["dst_ips"]:
                if not ip or ip in existing_values:
                    continue
                # 命名: `addr-{ip}` (跨 src/dst 复用 — 同 IP 只建一个对象)
                obj_name = f"addr-{ip}"
                if "/" in ip:
                    cmds.append(f'edit "{obj_name}"')
                    cmds.append("set type ipmask")
                    cmds.append(f"set subnet {ip}")
                    cmds.append("next")
                else:
                    cmds.append(f'edit "{obj_name}"')
                    cmds.append("set type iprange")
                    cmds.append(f"set start-ip {ip}")
                    cmds.append(f"set end-ip {ip}")
                    cmds.append("next")
        return cmds

    def _build_fortigate_addrgrp_block(self, policies, existing):
        """为每条策略建 src / dst 两个 addrgrp（成员为该策略的 IP 列表）

        与 _build_fortigate_address_block 配合：
          - address 名: addr-{ip}    (个体)
          - addrgrp 名: {rule_name}-src-group / -dst-group  (组，policy 引用此名)
        """
        cmds = []
        for p in policies:
            src_name = f"{p['rule_name']}-src-group"
            dst_name = f"{p['rule_name']}-dst-group"
            # 源组
            if p["src_ips"]:
                cmds.append(f'edit "{src_name}"')
                cmds.append("set member " + " ".join(
                    f'"addr-{ip}"' for ip in p["src_ips"]
                ))
                cmds.append("next")
            # 目的组
            if p["dst_ips"]:
                cmds.append(f'edit "{dst_name}"')
                cmds.append("set member " + " ".join(
                    f'"addr-{ip}"' for ip in p["dst_ips"]
                ))
                cmds.append("next")
        return cmds

    def _build_fortigate_service_block(self, policies, existing):
        existing_keys = {(s.protocol, s.dst_port): s.name for s in existing}
        cmds = []
        # 收集本批推送要建的所有 port（去重）
        ports_to_create = {}  # name -> proto
        for p in policies:
            for port in p["ports"]:
                if port.startswith("UDP:"):
                    port_v = port.split(":", 1)[1]
                    if ("udp", port_v) in existing_keys:
                        continue
                    ports_to_create[f"UDP-{port_v}"] = "udp"
                else:
                    if ("tcp", port) in existing_keys:
                        continue
                    ports_to_create[f"TCP-{port}"] = "tcp"
        # 输出
        for name, proto in ports_to_create.items():
            port_v = name.split("-", 1)[1]
            cmds.append(f'edit "{name}"')
            cmds.append("set protocol TCP/UDP/SCTP")
            if proto == "udp":
                cmds.append(f"set udp-portrange {port_v}")
            else:
                cmds.append(f"set tcp-portrange {port_v}")
            cmds.append("next")
        return cmds

    def _build_fortigate_service_group_block(self, policies):
        """为每条策略建 svc group，成员为该策略用到的所有服务对象名"""
        cmds = []
        for p in policies:
            if not p["ports"]:
                continue
            members = []
            for port in p["ports"]:
                if port.startswith("UDP:"):
                    members.append(f'"UDP-{port.split(":", 1)[1]}"')
                else:
                    members.append(f'"TCP-{port}"')
            cmds.append(f'edit "{p["rule_name"]}-svc-group"')
            cmds.append("set member " + " ".join(members))
            cmds.append("next")
        return cmds

    def _build_fortigate_schedule_block(self, policies, existing):
        cmds = []
        for p in policies:
            vu = p.get("valid_until", "")
            if not vu or "长期" in vu:
                continue
            date = vu.replace("-", "/")
            cmds.append(f'edit "截止{date}"')
            cmds.append(f"set end 23:59 {date}")
            cmds.append("set start 00:00 2021/01/01")
            cmds.append("next")
        return cmds

    def _build_fortigate_policy_block(self, policies):
        cmds = []
        for p in policies:
            cmds.append(f'edit {p["policy_id"]}')
            cmds.append(f'set srcintf "{p["src_zone"]}"')
            cmds.append(f'set dstintf "{p["dst_zone"]}"')
            # 源/目的地址用组名
            cmds.append(f'set srcaddr "{p["rule_name"]}-src-group"')
            cmds.append(f'set dstaddr "{p["rule_name"]}-dst-group"')
            cmds.append("set action accept")
            cmds.append(f'set schedule "{p.get("valid_until", "always") or "always"}"')
            cmds.append(f'set service "{p["rule_name"]}-svc-group"')
            cmds.append("set logtraffic enable")
            cmds.append("next")
        return cmds
