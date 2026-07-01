from __future__ import annotations

import re
import ipaddress
from typing import List, Dict, Set, Any, Tuple, Optional

from app.services.firewall_clients.base import (
    NetmikoFirewallClient, AddressObject, ServiceObject, FirewallPolicy
)


# ============================================================
# 1. 文本正则与行扫描解析器
# ============================================================

class H3CConfigParser:
    # 保持原有默认服务映射，用于标准服务解析
    DEFAULT_PORTS = {
        "FTP": "TCP:21", "SSH": "TCP:22", "TELNET": "TCP:23", "SMTP": "TCP:25",
        "DNS": "UDP:53\r\nTCP:53", "HTTP": "TCP:80", "HTTPS": "TCP:443",
        "ICMP": "ICMP", "MYSQL": "TCP:3306", "MS-SQL": "TCP:1433", "RDP": "TCP:3389"
    }

    @classmethod
    def parse(cls, config_text: str) -> Tuple[List[AddressObject], List[ServiceObject], List[FirewallPolicy]]:
        return cls._parse_addresses(config_text), cls._parse_services(config_text), cls._parse_policies(config_text)

    @classmethod
    def _mask_to_cidr(cls, mask: str) -> int:
        try:
            return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
        except Exception:
            return 32

    @classmethod
    def _parse_addresses(cls, text: str) -> List[AddressObject]:
        results = []
        pattern = re.compile(r'object-group\s+ip\s+address\s+"?([^"\n]+)"?\s*\n(.*?)(?=^\s*(?:object-group|quit|#))', re.M | re.S)
        
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            members = []
            for line in match.group(2).split('\n'):
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('description') or line.startswith('security-zone'): 
                    continue
                
                parts = line.split()
                if len(parts) < 3: 
                    continue
                
                # 兼容 0 network host address X / 0 network host name X
                if 'network host' in line:
                    members.append(parts[-1])
                elif 'network subnet' in line:
                    # 格式: 0 network subnet 10.2.129.200 255.255.255.252
                    cidr = cls._mask_to_cidr(parts[-1])
                    members.append(f"{parts[-2]}/{cidr}")
                elif 'network range' in line:
                    # 格式: 0 network range 10.2.132.110 10.2.132.117
                    members.append(f"{parts[-2]}-{parts[-1]}")
                elif 'group-object' in line:
                    members.append(f"@{parts[-1]}")
            
            results.append(AddressObject(name=name, type="group", value=name, members=members))
        return results

    @classmethod
    def _parse_services(cls, text: str) -> List[ServiceObject]:
        results = []
        # 加载基础预置服务
        for k, v in cls.DEFAULT_PORTS.items():
            results.append(ServiceObject(name=k, protocol="tcp", dst_port=v))

        pattern = re.compile(r'object-group\s+service\s+"?([^"\n]+)"?\s*\n(.*?)(?=^\s*(?:object-group|quit|#))', re.M | re.S)
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            
            for line in match.group(2).split('\n'):
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('description'): 
                    continue
                
                # 解析服务组内的多行定义
                # 示例: 0 service udp destination eq 123
                # 示例: 50 service tcp destination range 6810 6830
                parts = line.split()
                if 'service' in parts:
                    idx = parts.index('service')
                    if idx + 1 < len(parts):
                        proto = parts[idx + 1]
                        port_val = "any"
                        if 'eq' in parts:
                            port_val = parts[-1]
                        elif 'range' in parts:
                            port_val = f"{parts[-2]}-{parts[-1]}"
                        elif 'group-object' in line:
                            proto = "mix"
                            port_val = f"@{parts[-1]}"
                        
                        results.append(ServiceObject(name=name, protocol=proto, dst_port=port_val))
        return results

    @classmethod
    def _parse_policies(cls, text: str) -> List[FirewallPolicy]:
        results = []
        sec_block = re.search(r'security-policy\s+ip\s*\n(.*?)(?=^\s*return\s*$|^\s*#\s*$|\Z)', text, re.M | re.S)
        if not sec_block: 
            return results

        rule_pat = re.compile(r'rule\s+(?:\d+\s+)?name\s+"?([^"\n]+)"?\s*\n(.*?)(?=^\s*rule\s+(?:\d+\s+)?name|^\s*quit\s*$|^\s*#\s*$)', re.M | re.S)
        for match in rule_pat.finditer(sec_block.group(1)):
            header_line = match.group(0).split('\n')[0]
            name = match.group(1).strip()
            body = match.group(2)
            
            # 安全提取 Rule ID
            id_match = re.search(r'rule\s+(\d+)\s+name', header_line)
            policy_id = id_match.group(1) if id_match else ""

            src_zones = re.findall(r'source-zone\s+"?([^"\s]+)"?', body)
            dst_zones = re.findall(r'destination-zone\s+"?([^"\s]+)"?', body)
            
            src_addrs = []
            dst_addrs = []
            services = []
            
            # 精准行扫描，规避正则截断空格缺陷
            for line in body.split('\n'):
                line = line.strip()
                if not line: 
                    continue
                
                # 提取源 IP 元素 / 组
                if line.startswith('source-ip-host '):
                    src_addrs.append(line.split()[1])
                elif line.startswith('source-ip-subnet '):
                    p = line.split()
                    src_addrs.append(f"{p[1]}/{cls._mask_to_cidr(p[2])}")
                elif line.startswith('source-ip-range '):
                    p = line.split()
                    src_addrs.append(f"{p[1]}-{p[2]}")
                elif line.startswith('source-ip '):
                    src_addrs.append(line.split(' ', 1)[1].strip('"'))
                
                # 提取目的 IP 元素 / 组
                elif line.startswith('destination-ip-host '):
                    dst_addrs.append(line.split()[1])
                elif line.startswith('destination-ip-subnet '):
                    p = line.split()
                    dst_addrs.append(f"{p[1]}/{cls._mask_to_cidr(p[2])}")
                elif line.startswith('destination-ip-range '):
                    p = line.split()
                    dst_addrs.append(f"{p[1]}-{p[2]}")
                elif line.startswith('destination-ip '):
                    dst_addrs.append(line.split(' ', 1)[1].strip('"'))
                
                # 提取引用对象服务 与 内嵌 service-port 服务
                elif line.startswith('service-port '):
                    p = line.split()
                    proto = p[1].upper()
                    if 'eq' in p:
                        services.append(f"{proto}:{p[-1]}")
                    elif 'range' in p:
                        services.append(f"{proto}:{p[-2]}-{p[-1]}")
                elif line.startswith('service '):
                    services.append(line.split(' ', 1)[1].strip('"'))

            action = "pass" if "action pass" in body else "drop"
            enabled = "disable" not in body
            schedule = re.search(r'time-range\s+"?([^"\s]+)"?', body)

            results.append(FirewallPolicy(
                policy_id=policy_id, name=name,
                src_zone=src_zones[0] if src_zones else "any",
                dst_zone=dst_zones[0] if dst_zones else "any",
                src_addrs=src_addrs, dst_addrs=dst_addrs, services=services,
                schedule=schedule.group(1) if schedule else None,
                action=action, enabled=enabled
            ))
        return results


# ============================================================
# 2. 对象转换与安全反查索引
# ============================================================

class H3CObjectResolver:
    def __init__(self, addresses: List[AddressObject], services: List[ServiceObject]):
        self.addr_index = {a.name: a.members for a in addresses}
        
        # 将服务组汇聚为多值映射 List，防止单名覆盖
        self.svc_index: Dict[str, List[str]] = {}
        for s in services:
            val = f"{s.protocol.upper()}:{s.dst_port}"
            self.svc_index.setdefault(s.name, []).append(val)

    def resolve_policy(self, policy: FirewallPolicy) -> Dict[str, Any]:
        return {
            'policy_id': policy.policy_id,
            "name": policy.name,
            "src_zone": policy.src_zone,
            "dst_zone": policy.dst_zone,
            "src_ips": self._flatten_ips(policy.src_addrs),
            "dst_ips": self._flatten_ips(policy.dst_addrs),
            "ports": self._flatten_services(policy.services),
            "valid_until": policy.schedule or "",
            "action": policy.action
        }

    def _flatten_ips(self, items: List[str]) -> List[str]:
        real_ips = set()
        visited = set()
        for item in items: 
            self._walk_ip(item, real_ips, visited, 0)
        return list(real_ips)

    def _walk_ip(self, item: str, out: Set[str], visited: Set[str], depth: int) -> None:
        if depth > 10 or not item or item in visited: 
            return
        # 已经是标准网络元素
        if '/' in item or '-' in item or re.match(r'^\d+\.\d+\.\d+\.\d+$', item):
            out.add(item)
            return

        visited.add(item)
        clean_name = item.lstrip('@')
        if clean_name in self.addr_index:
            for member in self.addr_index[clean_name]:
                self._walk_ip(member, out, visited, depth + 1)

    def _flatten_services(self, items: List[str]) -> List[str]:
        real_svcs = set()
        for item in items:
            if ":" in item:  # 内嵌解析生成的描述 (e.g. TCP:111)
                real_svcs.add(item)
            elif item in self.svc_index:
                real_svcs.update(self.svc_index[item])
            else:
                real_svcs.add(item.upper())
        return list(real_svcs)

    def build_object_index(self) -> Dict[str, Dict[str, str]]:
        """构建可复用的现网对象索引 (执行安全过滤机制)"""
        addr_idx: Dict[str, str] = {}
        
        # 【安全边界优化】：只有当现网对象组内部仅有【单一原子元素】时，才允许反查引用
        # 从而彻底杜绝因为复用聚合对象组而造成的隐式网络放行漏洞
        for name, members in self.addr_index.items():
            if len(members) == 1:
                member = members[0].strip()
                if not member.startswith('@'):
                    addr_idx[member] = name

        svc_idx: Dict[str, str] = {}
        for name, port_list in self.svc_index.items():
            if len(port_list) == 1 and not port_list[0].startswith('MIX:'):
                svc_idx[port_list[0].lower()] = name

        return {
            "addresses": addr_idx,
            "services": svc_idx,
            "time_ranges": {},
        }


# ============================================================
# 3. 客户端与命令生成实现
# ============================================================

class H3CNetmikoClient(NetmikoFirewallClient):

    def _get_netmiko_device_type(self) -> str:
        return "hp_comware"

    def _get_show_config_command(self) -> str:
        return "display current-configuration"

    def _post_push_save(self) -> None:
        self.connection.send_command_timing("save force")

    def generate_commands(
        self,
        new_policies: List[Dict[str, Any]],
        object_index: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> List[str]:
        idx = object_index or {"addresses": {}, "services": {}, "time_ranges": {}}
        addr_existing = idx.get("addresses", {})
        svc_existing = idx.get("services", {})
        tr_existing = idx.get("time_ranges", {})

        addr_to_create: Dict[str, str] = {}
        svc_to_create: Dict[str, str] = {}
        tr_to_create: Dict[str, str] = {}

        # 新增：智能区间名称压缩工具
        def _compress_range_name(ip_key: str) -> str:
            if "-" in ip_key:
                parts = ip_key.split("-")
                if len(parts) == 2:
                    start_ip, end_ip = parts[0].strip(), parts[1].strip()
                    s_octets = start_ip.split(".")
                    e_octets = end_ip.split(".")
                    # 如果前三个 C 段完全相同，则压缩名称 (e.g., 10.2.179.127-129)
                    if len(s_octets) == 4 and len(e_octets) == 4 and s_octets[:3] == e_octets[:3]:
                        return f"{start_ip}-{e_octets[3]}"
            return ip_key
        def _normalize_ip(ip: str) -> Optional[str]:
            ip = ip.strip()
            if not ip:
                return None
            try:
                if "/" in ip:
                    net = ipaddress.ip_network(ip, strict=False)
                    return f"{net.network_address}/{net.prefixlen}"
                if "-" in ip:
                    return ip  # Range 保持原样作为 Key
                return str(ipaddress.ip_address(ip))
            except ValueError:
                return None

        def _normalize_port(port: str) -> Optional[Tuple[str, str]]:
            port = port.strip()
            if not port or port.upper() in ("ANY", "ALL"): 
                return None
            proto = "udp" if re.match(r'^UDP', port, re.I) else "tcp"
            body = re.sub(r'^(TCP|UDP)[:_-]', '', port, flags=re.I).strip()
            return (proto, body)

        # 扫描待建元素
        for p in new_policies:
            for ip in p.get("src_ips", []) or []:
                key = _normalize_ip(ip)
                if key and key not in addr_existing and key not in addr_to_create:
                    # Key 存全称 (用于内部逻辑), Value 存压缩后的简写 (用于对象组命名)
                    addr_to_create[key] = _compress_range_name(key)
            for ip in p.get("dst_ips", []) or []:
                key = _normalize_ip(ip)
                if key and key not in addr_existing and key not in addr_to_create:
                    addr_to_create[key] = _compress_range_name(key)
            for port in p.get("ports", []) or []:
                norm = _normalize_port(port)
                if not norm: 
                    continue
                proto, body = norm
                idx_key = f"{proto}:{body}"
                if idx_key not in svc_existing:
                    svc_to_create[idx_key] = f"{proto.upper()}-{body}"

            vu = (p.get("valid_until") or "").strip()
            if vu and vu != "长期":
                m = re.match(r'^(\d{4})[\-/.](\d{1,2})[\-/.](\d{1,2})$', vu)
                if m:
                    date_str = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                    if date_str not in tr_existing:
                        tr_to_create[date_str] = date_str

        cmds: List[str] = ["system-view"]
        # 2.1 下发地址对象组
        for key, name in addr_to_create.items():
            # 此时的 name 已经是 "10.2.179.127-129"
            cmds.append(f'object-group ip address "{name}"')
            if "/" in key:
                net = ipaddress.ip_network(key, strict=False)
                mask = net.netmask
                cmds.append(f" network subnet {net.network_address} {mask}")
            elif "-" in key:
                # 此时的 key 依然是 "10.2.179.127-10.2.179.129"
                a, b = key.split("-", 1)
                # 完美的实体配置命令：0 network range 10.2.179.127 10.2.179.129
                cmds.append(f" network range {a} {b}")
            else:
                cmds.append(f" network host address {key}")
            cmds.append("quit")

        # 2.2 下发服务对象组
        for idx_key, name in svc_to_create.items():
            proto, body = idx_key.split(":", 1)
            cmds.append(f'object-group service "{name}"')
            if "-" in body:
                a, b = body.split("-", 1)
                cmds.append(f" service {proto} destination range {a} {b}")
            else:
                cmds.append(f" ervice {proto} destination eq {body}")
            cmds.append("quit")

        # 2.3 下发时间范围
        for date_str, name in tr_to_create.items():
            cmds.append(f"time-range {name} from 00:00 2024/01/01 to 23:59 {date_str.replace('-', '/')}")

        # 2.4 下发安全策略本体
        cmds.append("security-policy ip")
        for p in new_policies:
            cmds.append(f"rule name {p['rule_name']}")
            
            # 纠正 action 动作映射错误映射（确保输出 pass/drop）
            act = p.get('action', 'pass')
            act = "pass" if act in ("pass", "accept",'permit') else "drop"
            cmds.append(f" action {act}")

            if p.get("src_zone") and p["src_zone"].lower() != "any":
                cmds.append(f" source-zone {p['src_zone']}")
            if p.get("dst_zone") and p["dst_zone"].lower() != "any":
                cmds.append(f" destination-zone {p['dst_zone']}")

            for ip in p.get("src_ips", []) or []:
                key = _normalize_ip(ip)
                ref = addr_existing.get(key) or addr_to_create.get(key) if key else None
                cmds.append(f' source-ip "{ref}"' if ref else f' source-ip "{ip}"')

            for ip in p.get("dst_ips", []) or []:
                key = _normalize_ip(ip)
                ref = addr_existing.get(key) or addr_to_create.get(key) if key else None
                cmds.append(f' destination-ip "{ref}"' if ref else f' destination-ip "{ip}"')

                # --- 原有的服务对象收集逻辑保持不变 ---
            port_names = []
            for port in p.get("ports", []) or []:
                norm = _normalize_port(port)
                if not norm:
                    continue
                idx_key = f"{norm[0]}:{norm[1]}"
                ref = svc_existing.get(idx_key) or svc_to_create.get(idx_key)
                if ref:
                    port_names.append(ref)

            # 【修复】：由同行空格合并改为【逐行下发】，适配华三现网真机语法
            for pname in port_names:
                cmds.append(f"  service {pname}")

                # --- 原有的时间范围引用等逻辑 ---
            vu = (p.get("valid_until") or "").strip()
            if vu and vu != "长期":
                m = re.match(r'^(\d{4})[\-/.](\d{1,2})[\-/.](\d{1,2})$', vu)
                if m:
                    d_key = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                    tr_name = tr_existing.get(d_key) or tr_to_create.get(d_key)
                    if tr_name: 
                        cmds.append(f" time-range {tr_name}")

        cmds.append("quit")
        cmds.append("return")
        return cmds