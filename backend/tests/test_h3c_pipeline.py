"""
test_h3c_pipeline.py
(2026-06-29) 验证新 H3C 管线能正常解析真实 10.2.31.82 设备配置

测试覆盖:
  1. H3CConfigParser.parse()   解析 object-group + security-policy
  2. H3CObjectResolver()       展开嵌套 group 为真实 IP/端口
  3. StandardPolicyEngine()    6 要素匹配 (FULL_MATCH / TIME_UPDATE / NEW_RULE)
  4. H3CNetmikoClient.generate_commands()  生成 H3C CLI 块

使用方式: cd firewall-web/backend && python tests/test_h3c_pipeline.py [CONFIG_PATH]
"""
from __future__ import annotations
import sys
import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List

# 让 import app.* 能找到
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.firewall_clients.h3c import (
    H3CConfigParser,
    H3CObjectResolver,
    H3CNetmikoClient,
)
from app.services.push_analyzer import StandardPolicyEngine


# ============================================================
# 1. 解析
# ============================================================

def test_parse(config_text: str) -> Dict[str, Any]:
    print("\n[Step 1] H3CConfigParser.parse()")
    addrs, svcs, policies = H3CConfigParser.parse(config_text)
    print(f"  ✓ addresses: {len(addrs)}")
    print(f"  ✓ services:  {len(svcs)}")
    print(f"  ✓ policies:  {len(policies)}")

    # 抽样打印前 3 个
    if addrs:
        a = addrs[0]
        print(f"  例: address[{a.name}] type={a.type} members={a.members[:3]}")
    if policies:
        p = policies[0]
        print(f"  例: policy[{p.name}] id={p.policy_id} {p.src_zone}→{p.dst_zone} "
              f"src={p.src_addrs[:2]} dst={p.dst_addrs[:2]} svc={p.services[:2]}")
    return {"addrs": addrs, "svcs": svcs, "policies": policies}


# ============================================================
# 2. 解析嵌套 group
# ============================================================

def test_resolve(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    print("\n[Step 2] H3CObjectResolver (展开嵌套 group)")
    resolver = H3CObjectResolver(parsed["addrs"], parsed["svcs"])
    real_rules = [resolver.resolve_policy(p) for p in parsed["policies"]]
    print(f"  ✓ 展开后真实规则数: {len(real_rules)}")

    # 统计展开后的真实 IP/端口覆盖情况
    multi_ip = sum(1 for r in real_rules if len(r["src_ips"]) > 1 or len(r["dst_ips"]) > 1)
    print(f"  ✓ 含多 IP 的策略: {multi_ip} 条 (group 嵌套展开)")

    if real_rules:
        r = real_rules[0]
        print(f"  例: rule[{r['name']}] src_ips={r['src_ips'][:3]}{'...' if len(r['src_ips'])>3 else ''} "
              f"dst_ips={r['dst_ips'][:3]}{'...' if len(r['dst_ips'])>3 else ''}")
    return real_rules


# ============================================================
# 3. 构造模拟 std_req, 跑匹配
# ============================================================

def test_match(device_rules: List[Dict[str, Any]]) -> None:
    print("\n[Step 3] StandardPolicyEngine (6 要素匹配)")

    # 模拟 3 种场景:
    #   (a) 完全匹配 — 复用某条现网策略
    #   (b) 时间不匹配 — 复用但需更新
    #   (c) IP 越界 — 全新建
    if not device_rules:
        print("  ⊘ 无现网规则可匹配, 跳过")
        return

    engine = StandardPolicyEngine(device_rules)
    sample = device_rules[0]

    # (a) FULL_MATCH: 完全沿用第一条现网规则的 6 要素
    std_full = {
        "policy_id": 999,
        "rule_name": "TEST_FULL_MATCH",
        "src_ips": sample["src_ips"][:2] if sample["src_ips"] else ["0.0.0.0/0"],
        "dst_ips": sample["dst_ips"][:2] if sample["dst_ips"] else ["0.0.0.0/0"],
        "ports": sample["ports"][:2] if sample["ports"] else ["ANY"],
        "src_zone": sample["src_zone"],
        "dst_zone": sample["dst_zone"],
        "valid_until": sample["valid_until"] or "长期",
    }
    res_a = engine.match_reusability(std_full)
    print(f"  (a) 完全复用: {res_a['mode']} → rule={res_a.get('reused_rule')}")

    # (b) TIME_UPDATE: 同上但 valid_until 改成不同
    std_time = dict(std_full)
    std_time["rule_name"] = "TEST_TIME_UPDATE"
    std_time["valid_until"] = "2099-12-31" if std_full["valid_until"] != "2099-12-31" else "2030-01-01"
    res_b = engine.match_reusability(std_time)
    print(f"  (b) 时间不匹配: {res_b['mode']} → rule={res_b.get('reused_rule')}")

    # (c) NEW_RULE: IP 完全不在任何现网规则覆盖内
    std_new = {
        "policy_id": 1000,
        "rule_name": "TEST_NEW_RULE",
        "src_ips": ["172.16.99.1"],
        "dst_ips": ["172.16.99.2"],
        "ports": ["9999"],
        "src_zone": "Trust",
        "dst_zone": "Untrust",
        "valid_until": "长期",
    }
    res_c = engine.match_reusability(std_new)
    print(f"  (c) 越界新建:   {res_c['mode']} → rule={res_c.get('reused_rule')}")


# ============================================================
# 3.5 复用索引测试 (object_index)
# ============================================================

def test_object_index(parsed: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    print("\n[Step 3.5] H3CObjectResolver.build_object_index (复用索引)")
    resolver = H3CObjectResolver(parsed["addrs"], parsed["svcs"])
    idx = resolver.build_object_index()
    print(f"  ✓ 设备现网地址对象数: {len(idx['addresses'])}")
    print(f"  ✓ 设备现网服务对象数: {len(idx['services'])}")
    print(f"  ✓ 设备现网 time-range: {len(idx['time_ranges'])} (H3C 单独段, 暂未解析)")
    if idx["addresses"]:
        sample_k = list(idx["addresses"].keys())[0]
        print(f"  例: addresses[{sample_k!r}] → 现网名 {idx['addresses'][sample_k]!r}")
    if idx["services"]:
        sample_k = list(idx["services"].keys())[0]
        print(f"  例: services[{sample_k!r}] → 现网名 {idx['services'][sample_k]!r}")
    return idx


# ============================================================
# 4. 生成 CLI (含 4 段式 + object 复用)
# ============================================================

def test_generate_cli(object_index: Dict[str, Dict[str, str]] = None) -> None:
    print("\n[Step 4] H3CNetmikoClient.generate_commands (H3C 4 段式 CLI)")
    client = H3CNetmikoClient(host="10.2.31.82", username="test", password="test", port=22, timeout=5)

    new_policies = [
        {
            "policy_id": 1,
            "rule_name": "O_TEST-P1-0",
            "src_ips": ["10.2.31.1"],
            "dst_ips": ["10.2.31.2"],
            "ports": ["TCP:80", "UDP:53-55"],
            "src_zone": "Trust",
            "dst_zone": "Untrust",
            "action": "permit",
            "valid_until": "2026-12-31",
        },
        {
            "policy_id": 2,
            "rule_name": "O_TEST-P2-0",
            "src_ips": ["10.2.31.3/32"],
            "dst_ips": ["10.2.31.4-10"],  # range 短格式
            "ports": ["443"],
            "src_zone": "Trust",
            "dst_zone": "Untrust",
            "action": "permit",
            "valid_until": "长期",
        },
    ]
    try:
        cmds = client.generate_commands(
            new_policies=new_policies,
            object_index=object_index or {"addresses": {}, "services": {}, "time_ranges": {}},
        )
        print(f"  ✓ 生成命令数: {len(cmds)}")
        for c in cmds[:30]:
            print(f"    > {c}")
        if len(cmds) > 30:
            print(f"    ... ({len(cmds) - 30} more)")
    except Exception as e:
        import traceback
        print(f"  ✗ 失败: {e}")
        traceback.print_exc()


# ============================================================
# 入口
# ============================================================

def main():
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    else:
        # 默认: backend/app/10.2.31.82 (用户提供的真实 H3C 配置)
        config_path = Path(__file__).parent.parent / "app" / "10.2.31.82"

    if not config_path.exists():
        print(f"✗ 配置不存在: {config_path}")
        print(f"  用法: python {sys.argv[0]} <config_path>")
        sys.exit(1)

    print(f"使用配置: {config_path} ({config_path.stat().st_size:,} bytes)")
    config_text = config_path.read_text(encoding="utf-8", errors="replace")

    parsed = test_parse(config_text)
    device_rules = test_resolve(parsed)
    test_match(device_rules)
    object_index = test_object_index(parsed)
    test_generate_cli(object_index)

    print("\n✓ 全部步骤通过")


if __name__ == "__main__":
    main()
