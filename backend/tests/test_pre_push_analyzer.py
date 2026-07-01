"""
PrePushAnalyzer 单测 — 6 要素校验 + 3 match_mode

覆盖:
  1. FULL_MATCH: zone+ip+port+time 全包容 → SKIP
  2. TIME_UPDATE: zone+ip+port 包容, time 不包容 → MODIFY
  3. NEW_RULE: zone 不一致 / IP 不包容 / port 不包容 → CREATE
  4. IP 边界: 10.1.1.5/32 ⊆ 10.0.0.0/8 ✓
  5. Port 边界: ["80"] ⊆ ["TCP-80"] ✓
  6. 多个老策略, 取第一个匹配的
  7. 空 fw_cache → 全 NEW_RULE
  8. Group 嵌套反查
"""
import pytest

from app.services.push_analyzer import PrePushAnalyzer, h3c_policies_to_fw_cache


# ============================================================
# 1. FULL_MATCH
# ============================================================

def test_full_match_all_inclusive():
    """zone+ip+port+time 全包容 → FULL_MATCH, push_script 为空"""
    fw_cache = {
        "rules": [
            {
                "name": "Rule_Sec_Prod_To_Test",
                "source_zone": "trust",
                "dest_zone": "untrust",
                "src_addrs": ["Obj-10.1.1.5"],
                "dst_addrs": ["Obj-192.168.1.1"],
                "services": ["TCP-80"],
                "schedule": "",
            }
        ],
        "addresses": [
            {"name": "Obj-10.1.1.5", "value": "10.1.1.5/32", "members": []},
            {"name": "Obj-192.168.1.1", "value": "192.168.1.1/32", "members": []},
        ],
        "time_ranges": [],
    }
    a = PrePushAnalyzer(fw_cache)
    result = a.analyze_single_policy({
        "device_source_zone": "trust",
        "device_dest_zone": "untrust",
        "source_ip": "10.1.1.5",
        "dest_ip": "192.168.1.1",
        "service": "80",
        "usage_time": "",
    })
    assert result["match_mode"] == "FULL_MATCH"
    assert result["reused_rule_name"] == "Rule_Sec_Prod_To_Test"
    assert result["push_script"] == []
    assert "完全复用" in result["audit_message"]


# ============================================================
# 2. TIME_UPDATE
# ============================================================

def test_time_update_zone_ip_port_ok_time_differs():
    """zone+ip+port 包容, time 不一致 → TIME_UPDATE"""
    fw_cache = {
        "rules": [
            {
                "name": "Rule_Old",
                "source_zone": "trust",
                "dest_zone": "untrust",
                "src_addrs": ["Obj-10.1.1.5"],
                "dst_addrs": ["Obj-192.168.1.1"],
                "services": ["TCP-80"],
                "schedule": "TR_Old",
            }
        ],
        "addresses": [
            {"name": "Obj-10.1.1.5", "value": "10.1.1.5/32", "members": []},
            {"name": "Obj-192.168.1.1", "value": "192.168.1.1/32", "members": []},
        ],
        "time_ranges": [{"name": "TR_Old", "text": "2025-12-31"}],
    }
    a = PrePushAnalyzer(fw_cache)
    result = a.analyze_single_policy({
        "device_source_zone": "trust",
        "device_dest_zone": "untrust",
        "source_ip": "10.1.1.5",
        "dest_ip": "192.168.1.1",
        "service": "80",
        "usage_time": "2027-06-30",
    })
    assert result["match_mode"] == "TIME_UPDATE"
    assert result["reused_rule_name"] == "Rule_Old"
    assert len(result["push_script"]) > 0
    assert "TR_UPDATE_Rule_Old" in "\n".join(result["push_script"])
    assert "时间不满足" in result["audit_message"]


# ============================================================
# 3. NEW_RULE
# ============================================================

def test_new_rule_zone_mismatch():
    """zone 不一致 → NEW_RULE"""
    fw_cache = {
        "rules": [
            {
                "name": "Rule_Other",
                "source_zone": "dmz",
                "dest_zone": "untrust",
                "src_addrs": ["Obj-10.1.1.5"],
                "dst_addrs": ["Obj-192.168.1.1"],
                "services": ["TCP-80"],
                "schedule": "",
            }
        ],
        "addresses": [
            {"name": "Obj-10.1.1.5", "value": "10.1.1.5/32", "members": []},
            {"name": "Obj-192.168.1.1", "value": "192.168.1.1/32", "members": []},
        ],
        "time_ranges": [],
    }
    a = PrePushAnalyzer(fw_cache)
    result = a.analyze_single_policy({
        "device_source_zone": "trust",  # 不一致
        "device_dest_zone": "untrust",
        "source_ip": "10.1.1.5",
        "dest_ip": "192.168.1.1",
        "service": "80",
    })
    assert result["match_mode"] == "NEW_RULE"
    assert result["reused_rule_name"] is None
    assert len(result["push_script"]) > 0


def test_new_rule_ip_not_subset():
    """req IP 不在 exist IP 内 → NEW_RULE"""
    fw_cache = {
        "rules": [
            {
                "name": "Rule_X",
                "source_zone": "trust",
                "dest_zone": "untrust",
                "src_addrs": ["Obj-10.1.1.5"],
                "dst_addrs": ["Obj-192.168.1.1"],
                "services": ["TCP-80"],
                "schedule": "",
            }
        ],
        "addresses": [
            {"name": "Obj-10.1.1.5", "value": "10.1.1.5/32", "members": []},
            {"name": "Obj-192.168.1.1", "value": "192.168.1.1/32", "members": []},
        ],
        "time_ranges": [],
    }
    a = PrePushAnalyzer(fw_cache)
    result = a.analyze_single_policy({
        "device_source_zone": "trust",
        "device_dest_zone": "untrust",
        "source_ip": "172.16.1.5",  # 不在 10.1.1.5/32 内
        "dest_ip": "192.168.1.1",
        "service": "80",
    })
    assert result["match_mode"] == "NEW_RULE"


def test_new_rule_port_not_subset():
    """port 不在 exist 内 → NEW_RULE"""
    fw_cache = {
        "rules": [
            {
                "name": "Rule_X",
                "source_zone": "trust",
                "dest_zone": "untrust",
                "src_addrs": ["Obj-10.1.1.5"],
                "dst_addrs": ["Obj-192.168.1.1"],
                "services": ["TCP-80"],
                "schedule": "",
            }
        ],
        "addresses": [
            {"name": "Obj-10.1.1.5", "value": "10.1.1.5/32", "members": []},
            {"name": "Obj-192.168.1.1", "value": "192.168.1.1/32", "members": []},
        ],
        "time_ranges": [],
    }
    a = PrePushAnalyzer(fw_cache)
    result = a.analyze_single_policy({
        "device_source_zone": "trust",
        "device_dest_zone": "untrust",
        "source_ip": "10.1.1.5",
        "dest_ip": "192.168.1.1",
        "service": "443",  # 不在 TCP-80 内
    })
    assert result["match_mode"] == "NEW_RULE"


# ============================================================
# 4. IP 边界
# ============================================================

def test_ip_subset_cidr_boundary():
    """10.1.1.5/32 ⊆ 10.0.0.0/8 (前缀包容)"""
    a = PrePushAnalyzer({
        "rules": [], "addresses": [], "time_ranges": []
    })
    assert a._ip_is_subset("10.1.1.5", ["10.0.0.0/8"]) is True
    assert a._ip_is_subset("10.1.1.5", ["10.1.0.0/16"]) is True
    assert a._ip_is_subset("10.1.1.5", ["10.1.1.0/24"]) is True
    assert a._ip_is_subset("10.1.1.5", ["10.1.1.5/32"]) is True
    assert a._ip_is_subset("10.2.1.5", ["10.1.0.0/16"]) is False  # 越界
    assert a._ip_is_subset("192.168.1.5", ["10.0.0.0/8"]) is False


def test_ip_subset_multi_ip_in_req():
    """需求 IP 是多 IP (换行/逗号分隔), 每个都要 ⊆ exist"""
    a = PrePushAnalyzer({"rules": [], "addresses": [], "time_ranges": []})
    assert a._ip_is_subset("10.1.1.5\n10.2.1.5", ["10.0.0.0/8"]) is True
    assert a._ip_is_subset("10.1.1.5, 192.168.1.5", ["10.0.0.0/8"]) is False


def test_ip_subset_any():
    """exist 含 'any' → 全包容"""
    a = PrePushAnalyzer({"rules": [], "addresses": [], "time_ranges": []})
    assert a._ip_is_subset("10.1.1.5", ["any"]) is True
    assert a._ip_is_subset("192.168.1.5", ["any"]) is True


# ============================================================
# 5. Port 边界
# ============================================================

def test_ports_subset_basic():
    a = PrePushAnalyzer({"rules": [], "addresses": [], "time_ranges": []})
    assert a._ports_are_subset({"80"}, ["TCP-80"]) is True
    assert a._ports_are_subset({"80"}, ["TCP-443"]) is False
    assert a._ports_are_subset({"80", "443"}, ["TCP-80"]) is False  # 443 不在
    assert a._ports_are_subset({"80", "443"}, ["TCP-80", "TCP-443"]) is True
    assert a._ports_are_subset({"80"}, ["any"]) is True


# ============================================================
# 6. 多个老策略, 取第一个匹配的
# ============================================================

def test_multiple_rules_first_match_wins():
    """多个候选 rule, 第一个匹配的胜出 (按 fw_cache 顺序)"""
    fw_cache = {
        "rules": [
            {
                "name": "Rule_1_Specific",
                "source_zone": "trust", "dest_zone": "untrust",
                "src_addrs": ["Obj-10.1.1.5"], "dst_addrs": ["Obj-192.168.1.1"],
                "services": ["TCP-80"], "schedule": "",
            },
            {
                "name": "Rule_2_Generic",
                "source_zone": "trust", "dest_zone": "untrust",
                "src_addrs": ["Obj-10.0.0.0/8-Net"], "dst_addrs": ["Obj-Any"],
                "services": ["Any-Svc"], "schedule": "",
            },
        ],
        "addresses": [
            {"name": "Obj-10.1.1.5", "value": "10.1.1.5/32", "members": []},
            {"name": "Obj-192.168.1.1", "value": "192.168.1.1/32", "members": []},
            {"name": "Obj-10.0.0.0/8-Net", "value": "10.0.0.0/8", "members": []},
            {"name": "Obj-Any", "value": "any", "members": []},
        ],
        "time_ranges": [],
    }
    a = PrePushAnalyzer(fw_cache)
    result = a.analyze_single_policy({
        "device_source_zone": "trust", "device_dest_zone": "untrust",
        "source_ip": "10.1.1.5", "dest_ip": "192.168.1.1", "service": "80",
    })
    # 应该命中 Rule_1_Specific (更具体)
    assert result["match_mode"] == "FULL_MATCH"
    assert result["reused_rule_name"] == "Rule_1_Specific"


# ============================================================
# 7. 空 fw_cache
# ============================================================

def test_empty_fw_cache_all_new_rule():
    """空 fw_cache → 所有策略都 NEW_RULE"""
    a = PrePushAnalyzer({"rules": [], "addresses": [], "time_ranges": []})
    result = a.analyze_single_policy({
        "device_source_zone": "trust", "device_dest_zone": "untrust",
        "source_ip": "10.1.1.5", "dest_ip": "192.168.1.1", "service": "80",
    })
    assert result["match_mode"] == "NEW_RULE"
    assert "未匹配" in result["audit_message"]


def test_none_fw_cache_all_new_rule():
    """传 None → 不报错, 全部 NEW_RULE"""
    a = PrePushAnalyzer(None)
    result = a.analyze_single_policy({
        "device_source_zone": "trust", "device_dest_zone": "untrust",
        "source_ip": "10.1.1.5", "dest_ip": "192.168.1.1", "service": "80",
    })
    assert result["match_mode"] == "NEW_RULE"


# ============================================================
# 8. Group 嵌套反查
# ============================================================

def test_group_nested_address_resolution():
    """rule 引用 group, group 引用多个 IP, IP 都要包容"""
    fw_cache = {
        "rules": [
            {
                "name": "Rule_Group",
                "source_zone": "trust", "dest_zone": "untrust",
                "src_addrs": ["Group-Producers"],
                "dst_addrs": ["Group-Consumers"],
                "services": ["TCP-80"],
                "schedule": "",
            }
        ],
        "addresses": [
            {"name": "Group-Producers", "value": "", "members": ["@Subnet-A", "@Subnet-B"]},
            {"name": "Group-Consumers", "value": "", "members": ["10.99.0.0/16"]},
            {"name": "Subnet-A", "value": "10.1.0.0/16", "members": []},
            {"name": "Subnet-B", "value": "10.2.0.0/16", "members": []},
        ],
        "time_ranges": [],
    }
    a = PrePushAnalyzer(fw_cache)
    # req 在 10.1.0.0/16 内 → 包容
    result = a.analyze_single_policy({
        "device_source_zone": "trust", "device_dest_zone": "untrust",
        "source_ip": "10.1.1.5", "dest_ip": "10.99.1.5", "service": "80",
    })
    assert result["match_mode"] == "FULL_MATCH"
    # req 在 10.3.0.0/16 (不在 group 内) → 不匹配
    result2 = a.analyze_single_policy({
        "device_source_zone": "trust", "device_dest_zone": "untrust",
        "source_ip": "10.3.1.5", "dest_ip": "10.99.1.5", "service": "80",
    })
    assert result2["match_mode"] == "NEW_RULE"


# ============================================================
# 9. Time 边界
# ============================================================

def test_time_subset_semantics():
    a = PrePushAnalyzer({"rules": [], "addresses": [], "time_ranges": []})
    # exist 空 → 包容
    assert a._time_is_subset("2027-01-01", "") is True
    assert a._time_is_subset("2027-01-01", "any") is True
    assert a._time_is_subset("2027-01-01", "always") is True
    # 相同 → 包容
    assert a._time_is_subset("2027-01-01", "2027-01-01") is True
    # 不同 → 不包容
    assert a._time_is_subset("2027-01-01", "2025-12-31") is False
    # req 空 → 包容 (无时间要求)
    assert a._time_is_subset("", "2025-12-31") is True


# ============================================================
# 10. H3C CLI 生成格式
# ============================================================

def test_time_update_cli_format():
    cli = PrePushAnalyzer._generate_time_update_cli("Rule_X", "2027-06-30")
    joined = "\n".join(cli)
    assert "time-range TR_UPDATE_Rule_X" in joined
    assert "2027-06-30" in joined
    assert "rule name Rule_X" in joined
    assert "quit" in joined


def test_full_new_cli_format():
    cli = PrePushAnalyzer._generate_full_new_cli({
        "device_source_zone": "trust",
        "device_dest_zone": "untrust",
        "source_ip": "10.1.1.5",
        "dest_ip": "192.168.1.1",
        "service": "80",
        "rule_name": "AUTO_NEW_1",
    })
    joined = "\n".join(cli)
    assert "security-policy ip" in joined
    assert "source-zone trust" in joined
    assert "destination-zone untrust" in joined
    assert "10.1.1.5" in joined
    assert "192.168.1.1" in joined
    assert "AUTO_NEW_1" in joined
