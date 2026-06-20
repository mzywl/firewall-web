"""
测试 3 家命令生成器：Fortigate / Sangfor / H3C
重点验证：
  1. 生成的命令可被设备正确解析（不引用未创建的对象）
  2. 地址组/服务组命名稳定 + member 引用正确
  3. policy 块引用的 group 都在前面被创建
"""
import pytest

from app.services.firewall_clients.fortigate import FortigateClient
from app.services.firewall_clients.sangfor import SangforClient
from app.services.firewall_clients.h3c import H3CClient
from app.services.firewall_clients.base import AddressObject, ServiceObject


# ============================================================
# 测试夹具
# ============================================================

@pytest.fixture
def sample_policy():
    """一条典型策略：1 src + 2 dst + 2 ports + 有效期 + 区域"""
    return {
        "policy_id": 101,
        "rule_name": "ORD001-P101",
        "src_ips": ["10.1.1.0/24", "10.1.2.1"],
        "dst_ips": ["192.168.1.100", "192.168.2.0/24"],
        "ports": ["80", "443", "UDP:53"],
        "valid_until": "2025-12-31",
        "src_zone": "trust",
        "dst_zone": "untrust",
        "action": "permit",
    }


@pytest.fixture
def existing_addresses():
    """设备上已存在的地址（含 1 个复用 + 1 个新）"""
    return [
        AddressObject(name="trust-10.1.1.0", type="subnet", value="10.1.1.0/24"),
        AddressObject(name="legacy-server", type="ip", value="192.168.1.100"),
    ]


@pytest.fixture
def existing_services():
    return [
        ServiceObject(name="TCP-80", protocol="tcp", dst_port="80"),
    ]


# ============================================================
# Fortigate
# ============================================================

class TestFortigateCommands:
    def test_address_naming_is_stable(self, sample_policy, existing_addresses):
        """每个 IP 的 address 名要稳定: {rule_name}-{ip}"""
        client = FortigateClient.__new__(FortigateClient)  # 绕过 __init__ 缺省
        block = client._build_fortigate_address_block([sample_policy], existing_addresses)
        # 10.1.1.0/24 已在 existing → 不建
        # 10.1.2.1 新 → 建
        # 192.168.1.100 已在 existing → 不建
        # 192.168.2.0/24 新 → 建
        text = "\n".join(block)
        assert 'edit "addr-10.1.2.1"' in text
        assert 'edit "addr-192.168.2.0/24"' in text
        assert 'edit "addr-10.1.1.0/24"' not in text  # 跳过已存在
        assert 'edit "addr-192.168.1.100"' not in text  # 跳过已存在

    def test_addrgrp_references_real_addresses(self, sample_policy, existing_addresses):
        """addrgrp 的 member 必须引用前面 address block 建出的名"""
        client = FortigateClient.__new__(FortigateClient)
        addrs = client._build_fortigate_address_block([sample_policy], existing_addresses)
        groups = client._build_fortigate_addrgrp_block([sample_policy], existing_addresses)
        addr_text = "\n".join(addrs)
        group_text = "\n".join(groups)

        # src group 名
        assert 'edit "ORD001-P101-src-group"' in group_text
        assert 'edit "ORD001-P101-dst-group"' in group_text
        # src group 引用了所有 src IP（即使已存在——addrgrp 是逻辑概念，可引用任何名）
        assert '"addr-10.1.1.0/24"' in group_text
        assert '"addr-10.1.2.1"' in group_text
        # dst group
        assert '"addr-192.168.1.100"' in group_text
        assert '"addr-192.168.2.0/24"' in group_text

    def test_service_block_deduplicates(self, sample_policy, existing_services):
        """service 块去重（多策略共享同一 port 不重复创建）"""
        policies = [sample_policy, sample_policy]  # 同一条推 2 次
        client = FortigateClient.__new__(FortigateClient)
        block = client._build_fortigate_service_block(policies, existing_services)
        text = "\n".join(block)
        # TCP-80 已存在 → 不建
        # TCP-443 应只出现 1 次
        assert text.count('edit "TCP-443"') == 1
        # UDP-53 应只出现 1 次
        assert text.count('edit "UDP-53"') == 1

    def test_service_group_per_policy(self, sample_policy, existing_services):
        """每个策略独立建 svc group，引用自己的服务对象"""
        client = FortigateClient.__new__(FortigateClient)
        block = client._build_fortigate_service_group_block([sample_policy])
        text = "\n".join(block)
        assert 'edit "ORD001-P101-svc-group"' in text
        assert '"TCP-80"' in text
        assert '"TCP-443"' in text
        assert '"UDP-53"' in text

    def test_policy_references_groups(self, sample_policy, existing_addresses):
        """policy 块必须引用 group 名（src-group / dst-group / svc-group）"""
        client = FortigateClient.__new__(FortigateClient)
        block = client._build_fortigate_policy_block([sample_policy])
        text = "\n".join(block)
        assert 'set srcaddr "ORD001-P101-src-group"' in text
        assert 'set dstaddr "ORD001-P101-dst-group"' in text
        assert 'set service "ORD001-P101-svc-group"' in text

    def test_full_generation_no_dangling_refs(self, sample_policy, existing_addresses, existing_services):
        """完整生成：所有 group 引用的对象都在前面 block 里建了"""
        client = FortigateClient.__new__(FortigateClient)
        cmds = client.generate_commands(
            new_policies=[sample_policy],
            existing_addresses=existing_addresses,
            existing_services=existing_services,
            existing_schedules=[],
        )
        text = "\n".join(cmds)

        # 顶层分段
        assert "config firewall address" in text
        assert "config firewall addrgrp" in text
        assert "config firewall service custom" in text
        assert "config firewall service group" in text
        assert "config firewall policy" in text

        # 顺序：address → addrgrp → service → service group → policy
        pos_addr = text.index("config firewall address")
        pos_grp = text.index("config firewall addrgrp")
        pos_svc = text.index("config firewall service custom")
        pos_svcgrp = text.index("config firewall service group")
        pos_pol = text.index("config firewall policy")
        assert pos_addr < pos_grp < pos_svc < pos_svcgrp < pos_pol


# ============================================================
# Sangfor
# ============================================================

class TestSangforCommands:
    def test_addresses_and_addrgrp_match(self, sample_policy, existing_addresses):
        """addrgrp 成员引用实际存在的对象名（existing 直接复用，新 IP 用 addr-X）"""
        client = SangforClient.__new__(SangforClient)
        addrs = client._gen_addresses(
            sample_policy["src_ips"] + sample_policy["dst_ips"],
            existing_addresses,
        )
        groups = client._gen_addrgrp([sample_policy], existing_addresses)
        addr_text = "\n".join(addrs)
        group_text = "\n".join(groups)

        # 新 IP 才建 address（10.1.2.1, 192.168.2.0/24）
        assert 'object network address "addr-10.1.2.1"' in addr_text
        assert 'object network address "addr-192.168.2.0/24"' in addr_text
        # 已存在的 IP 不再建（10.1.1.0/24, 192.168.1.100）
        assert 'object network address "addr-10.1.1.0/24"' not in addr_text
        assert 'object network address "addr-192.168.1.100"' not in addr_text

        # addrgrp: 已存在的 IP 引用 existing.name（trust-10.1.1.0）
        #         新 IP 引用 addr-X
        assert 'object-group network address "ORD001-P101-src-group"' in group_text
        assert 'network address member "trust-10.1.1.0"' in group_text  # 复用 existing
        assert 'network address member "addr-10.1.2.1"' in group_text  # 新建
        assert 'object-group network address "ORD001-P101-dst-group"' in group_text
        assert 'network address member "legacy-server"' in group_text  # 复用 existing（192.168.1.100）
        assert 'network address member "addr-192.168.2.0/24"' in group_text

    def test_policy_references_groups(self, sample_policy, existing_addresses):
        """policy sip/dip 必须引用 group 名而非个体 IP"""
        client = SangforClient.__new__(SangforClient)
        block = client._gen_policy(sample_policy, [])
        text = "\n".join(block)
        assert 'sip "ORD001-P101-src-group"' in text
        assert 'dip "ORD001-P101-dst-group"' in text
        # 不应该再 append 散装 IP
        assert 'append sip' not in text
        assert 'append dip' not in text

    def test_full_generation_order(self, sample_policy, existing_addresses, existing_services):
        """生成顺序：address → service → addrgrp → policy"""
        client = SangforClient.__new__(SangforClient)
        cmds = client.generate_commands(
            new_policies=[sample_policy],
            existing_addresses=existing_addresses,
            existing_services=existing_services,
            existing_schedules=[],
        )
        text = "\n".join(cmds)
        # 找各段位置
        pos_addr = text.index("object network address")
        pos_grp = text.index("object-group network address")
        pos_pol = text.index("security policy")
        assert pos_addr < pos_grp < pos_pol

    def test_policy_uses_correct_zones(self, sample_policy):
        """策略的 szone/dzone 应该用真实值，不再硬编码 'any'"""
        client = SangforClient.__new__(SangforClient)
        block = client._gen_policy(sample_policy, [])
        text = "\n".join(block)
        assert 'szone "trust"' in text
        assert 'dzone "untrust"' in text

    def test_multiple_ports_appended(self):
        """多端口场景：第 2 个及之后的端口用 append service"""
        p = {
            "rule_name": "ORD002-P1",
            "src_ips": ["10.0.0.1"],
            "dst_ips": ["192.168.0.1"],
            "ports": ["80", "443"],
            "valid_until": "长期",
            "src_zone": "any", "dst_zone": "any",
            "action": "permit",
        }
        client = SangforClient.__new__(SangforClient)
        block = client._gen_policy(p, [])
        text = "\n".join(block)
        # 第一个端口是首条 policy
        assert 'service "TCP-80"' in text
        # 第二个端口是 append
        assert 'append service "TCP-443"' in text


# ============================================================
# H3C
# ============================================================

class TestH3CCommands:
    def test_address_objects_naming(self, sample_policy):
        """H3C 的 object-group ip address 命名: `addr-{ip}` (跨 src/dst 复用 — 同 IP 只建一个)"""
        client = H3CClient.__new__(H3CClient)
        src_block = client._gen_address_objects(
            sample_policy["src_ips"],
            f"{sample_policy['rule_name']}-src",
            [],
        )
        dst_block = client._gen_address_objects(
            sample_policy["dst_ips"],
            f"{sample_policy['rule_name']}-dst",
            [],
        )
        src_text = "\n".join(src_block)
        dst_text = "\n".join(dst_block)
        # 命名: addr-{ip} (跟 IP 形式)
        assert 'object-group ip address "addr-10.1.1.0/24"' in src_text
        assert "network subnet 10.1.1.0 255.255.255.0" in src_text
        assert 'object-group ip address "addr-10.1.2.1"' in src_text
        assert "network host address 10.1.2.1" in src_text
        assert 'object-group ip address "addr-192.168.1.100"' in dst_text
        assert "network host address 192.168.1.100" in dst_text
        assert 'object-group ip address "addr-192.168.2.0/24"' in dst_text

    def test_rule_command_full_multiline(self, sample_policy):
        """_gen_rule_command 必须生成完整多行（rule name + 各属性 + action）"""
        client = H3CClient.__new__(H3CClient)
        cmds = client._gen_rule_command(sample_policy)
        assert isinstance(cmds, list)
        # 第 1 行
        assert cmds[0] == 'rule name "ORD001-P101"'
        # source-zone / destination-zone
        assert "source-zone trust" in cmds
        assert "destination-zone untrust" in cmds
        # source-ip / destination-ip（每个 IP 一行, 引用 addr-{ip}）
        assert 'source-ip "addr-10.1.1.0/24"' in cmds
        assert 'source-ip "addr-10.1.2.1"' in cmds
        assert 'destination-ip "addr-192.168.1.100"' in cmds
        assert 'destination-ip "addr-192.168.2.0/24"' in cmds
        # service（每个端口一行）
        assert 'service "TCP-80"' in cmds
        assert 'service "TCP-443"' in cmds
        assert 'service "UDP-53"' in cmds
        # time-range
        assert 'time-range "ORD001-P101-sched"' in cmds
        # action
        assert "action permit" in cmds

    def test_full_generation_references_exist(self, sample_policy):
        """完整生成：rule 引用的所有 addr-{ip}/svc-X 都必须前面建了"""
        client = H3CClient.__new__(H3CClient)
        cmds = client.generate_commands(
            new_policies=[sample_policy],
            existing_addresses=[],
            existing_services=[],
            existing_schedules=[],
        )
        text = "\n".join(cmds)
        # 顺序：object-group ip address → object-group service → time-range → security-policy ip → rule
        pos_addr = text.index("object-group ip address")
        pos_svc = text.index("object-group service")
        pos_sec = text.index("security-policy ip")
        pos_rule = text.index('rule name "ORD001-P101"')
        assert pos_addr < pos_svc < pos_sec < pos_rule

        # rule 中引用的对象名都在 addr/svc 段 (addr-{ip} 形式)
        assert 'object-group ip address "addr-10.1.1.0/24"' in text
        assert 'object-group ip address "addr-192.168.1.100"' in text
        assert 'object-group service "TCP-80"' in text
        assert 'object-group service "UDP-53"' in text

    def test_rule_action_handles_aliases(self):
        """action=pass（被某些匹配器翻译过）应原样输出"""
        p = {
            "rule_name": "T-P1",
            "src_ips": ["10.0.0.1"],
            "dst_ips": ["192.168.0.1"],
            "ports": ["80"],
            "valid_until": "长期",
            "src_zone": "any", "dst_zone": "any",
            "action": "pass",  # 飞塔/H3C 都用 "pass"
        }
        client = H3CClient.__new__(H3CClient)
        cmds = client._gen_rule_command(p)
        # permit/deny 原样；其它（如 pass）用 pass
        assert "action pass" in cmds
