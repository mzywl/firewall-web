"""网神防火墙客户端

参照旧版 /home/lishiyu/output/lishiyu/cx/网神防火墙策略.py
- 拉配置: show running config
- 地址: object network address "..." network-object host/subnet/range
- 端口: object service custom "TCP-..." service-item tcp/udp ...
- 策略: security policy "名称" sip/dip/service/schedule/action
- 追加: security policy "名称" append sip/dip/service
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


class SangforClient(FirewallClient):

    def _read_version(self) -> str:
        self.shell.send(self.encode("show version\n"))
        return self._recv_until(">", idle_pause=0.5, max_wait=5)

    def _config_command(self) -> Tuple[str, str]:
        return "show running config", "cloud basic configuration"

    def parse_config(
        self, text: str
    ) -> Tuple[List[AddressObject], List[ServiceObject], List[FirewallPolicy]]:
        addresses = self._parse_addresses(text)
        services = self._parse_services(text)
        policies = self._parse_policies(text)
        return addresses, services, policies

    def _parse_addresses(self, text: str) -> List[AddressObject]:
        result = []
        pattern = re.compile(
            r'object\s+network\s+address\s+"([^"]+)"\s*\n'
            r'(.*?)(?=^object\s+network\s+address\s+"|^\s*$)',
            re.M | re.S,
        )
        for m in pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            for line in body.split("\n"):
                if "host" in line and "host-name" not in line:
                    val = line.split()[-1]
                    result.append(AddressObject(name=name, type="ip", value=val))
                elif "subnet" in line:
                    parts = line.split()
                    val = f"{parts[-2]}/{parts[-1]}"
                    result.append(AddressObject(name=name, type="subnet", value=val))
                elif "range" in line:
                    parts = line.split()
                    val = f"{parts[-2]}-{parts[-1]}"
                    result.append(AddressObject(name=name, type="range", value=val))
        return result

    def _parse_services(self, text: str) -> List[ServiceObject]:
        result = []
        pattern = re.compile(
            r'object\s+service\s+custom\s+"(TCP-[^"]+|UDP-[^"]+)"\s*\n'
            r'service-item\s+(tcp|udp)\s+src-port\s+\d+\s+\d+\s+dst-port\s+([\d-]+)',
        )
        for m in pattern.finditer(text):
            result.append(ServiceObject(
                name=m.group(1), protocol=m.group(2), dst_port=m.group(3),
            ))
        return result

    def _parse_policies(self, text: str) -> List[FirewallPolicy]:
        result = []
        # 简化: 抓 security policy "名称" ... 一段
        pattern = re.compile(
            r'security\s+policy\s+"([^"]+)"\s*\n'
            r'sip\s+([^\n]+)\s*\n'
            r'dip\s+([^\n]+)\s*\n'
            r'szone\s+"?([^"\s]+)"?\s*\n'
            r'dzone\s+"?([^"\s]+)"?\s*\n'
            r'service\s+"?([^"\s]+)"?\s*\n'
            r'action\s+(\w+)\s*\n'
            r'(enable|disable)',
        )
        for m in pattern.finditer(text):
            result.append(FirewallPolicy(
                policy_id=m.group(1), name=m.group(1),
                src_zone=m.group(4), dst_zone=m.group(5),
                src_addrs=m.group(2).split(), dst_addrs=m.group(3).split(),
                services=[m.group(6)] if m.group(6) != "any" else [],
                schedule=None,
                action="accept" if "permit" in m.group(7) else "deny",
                enabled=m.group(9) == "enable",
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
        cmds.append("config terminal")
        # 1) 地址（个体）
        for p in new_policies:
            cmds.extend(self._gen_addresses(p["src_ips"] + p["dst_ips"], existing_addresses))
        # 2) 服务
        for p in new_policies:
            cmds.extend(self._gen_services(p["ports"], existing_services))
        # 3) 地址组（每条策略 src / dst 各一组，policy 引用组）
        cmds.extend(self._gen_addrgrp(new_policies, existing_addresses))
        # 4) 策略（引用 group 而非个体 IP）
        for p in new_policies:
            cmds.extend(self._gen_policy(p, existing_schedules))
        cmds.append("end")
        return cmds

    def _gen_addresses(self, ips: List[str], existing: List[AddressObject]) -> List[str]:
        existing_values = {a.value: a.name for a in existing if a.value}
        cmds = []
        for ip in ips:
            if not ip or ip in existing_values:
                continue
            if "/" in ip:
                net, mask = ip.split("/")
                cmds.append(f'object network address "addr-{ip}"')
                cmds.append(f"network-object  network {net} {mask}")
                cmds.append("exit")
            elif "-" in ip:
                a, b = ip.split("-")
                cmds.append(f'object network address "addr-{ip}"')
                cmds.append(f"network-object  range {a} {b}")
                cmds.append("exit")
            else:
                cmds.append(f'object network address "addr-{ip}"')
                cmds.append(f'network-object  host "{ip}"')
                cmds.append("exit")
        return cmds

    def _gen_services(self, ports: List[str], existing: List[ServiceObject]) -> List[str]:
        existing_keys = {(s.protocol, s.dst_port): s.name for s in existing}
        cmds = []
        for p in ports:
            if p.startswith("UDP:"):
                port = p.split(":", 1)[1]
                if ("udp", port) in existing_keys:
                    continue
                if "-" in port:
                    a, b = port.split("-")
                    cmds.append(f'object service custom "UDP-{port}"')
                    cmds.append(f"service-item udp src-port 1 65535 dst-port {a} {b}")
                else:
                    cmds.append(f'object service custom "UDP-{port}"')
                    cmds.append(f"service-item udp src-port 1 65535 dst-port {port} {port}")
                cmds.append("exit")
            else:
                if ("tcp", p) in existing_keys:
                    continue
                if "-" in p:
                    a, b = p.split("-")
                    cmds.append(f'object service custom "TCP-{p}"')
                    cmds.append(f"service-item tcp src-port 1 65535 dst-port {a} {b}")
                else:
                    cmds.append(f'object service custom "TCP-{p}"')
                    cmds.append(f"service-item tcp src-port 1 65535 dst-port {p} {p}")
                cmds.append("exit")
        return cmds

    def _gen_addrgrp(self, policies, existing: List[AddressObject]) -> List[str]:
        """为每条策略建 src / dst 两个地址组，成员为该策略的 IP 列表

        Sangfor 的 address group 语法: object-group network address "name"
          network address member "addr-X"

        重要：member 必须引用 _gen_addresses 实际建出来的对象名：
          - 已存在的 IP（existing.value 命中）→ 直接用 existing.name
          - 新 IP → "addr-{ip}"
        """
        # 建立 IP → 对象名映射
        existing_values = {a.value: a.name for a in existing if a.value}
        ip_to_obj = {}  # ip -> obj name
        all_ips = set()
        for p in policies:
            all_ips.update(p["src_ips"])
            all_ips.update(p["dst_ips"])
        for ip in all_ips:
            if ip in existing_values:
                ip_to_obj[ip] = existing_values[ip]
            else:
                ip_to_obj[ip] = f"addr-{ip}"

        cmds = []
        for p in policies:
            if p["src_ips"]:
                cmds.append(f'object-group network address "{p["rule_name"]}-src-group"')
                for ip in p["src_ips"]:
                    cmds.append(f'network address member "{ip_to_obj[ip]}"')
                cmds.append("exit")
            if p["dst_ips"]:
                cmds.append(f'object-group network address "{p["rule_name"]}-dst-group"')
                for ip in p["dst_ips"]:
                    cmds.append(f'network address member "{ip_to_obj[ip]}"')
                cmds.append("exit")
        return cmds

    def _gen_policy(self, p: Dict[str, Any], existing_schedules: List) -> List[str]:
        name = p["rule_name"]
        cmds = []
        # 引用地址组（而不是个体 IP）
        src_grp = f'"{name}-src-group"' if p["src_ips"] else '"any"'
        dst_grp = f'"{name}-dst-group"' if p["dst_ips"] else '"any"'
        first_svc = f'"TCP-{p["ports"][0]}"' if p["ports"] and not p["ports"][0].startswith("UDP:") else \
                    f'"UDP-{p["ports"][0].split(":")[1]}"' if p["ports"] else '"any"'
        cmds.append(
            f'security policy "{name}" sip {src_grp} dip {dst_grp} '
            f'szone "{p.get("src_zone", "any")}" dzone "{p.get("dst_zone", "any")}" '
            f'service {first_svc} action permit enable'
        )
        cmds.append(f'security policy "{name}" log enable')
        # 追加其余端口（多端口情况）
        for port in p["ports"][1:]:
            obj = f'"UDP-{port.split(":")[1]}"' if port.startswith("UDP:") else f'"TCP-{port}"'
            cmds.append(f'security policy "{name}" append service {obj}')
        # 时间
        vu = p.get("valid_until", "")
        if vu and "长期" not in vu:
            sched_name = f'"截止{vu}"'
            cmds.append(f'security policy "{name}" schedule {sched_name}')
        return cmds
