"""
测试 3 mode 隔离 (重构.md §3)

覆盖:
- force_push 模式: 整条 CREATED
- reuse_objects 模式: 整条 CREATED (跟 force_push 当前行为一致, 语义区分)
- deduplicate 模式: 4 维 HASH 命中 → REUSED (整条跳过)
- deduplicate 模式: 4 维 HASH 不命中 → CREATED
- 3 mode 互不干扰
- 非法 mode 报错
- PushMode enum 包含 3 个值
"""
import pytest
from app.core.policy_matcher import (
    PolicyMatcher, MatchAction, MatchResult, ObjectReuse
)
from app.services.firewall_clients.base import (
    AddressObject, ServiceObject, ScheduleObject, FirewallPolicy
)
from app.models import PushMode


# ============================================================
# 工厂: 造"设备上现有的"地址/服务/时间/策略
# ============================================================

def _existing_addr(name: str, value: str) -> AddressObject:
    return AddressObject(name=name, type="ip", value=value)


def _existing_svc(name: str, proto: str, port: str) -> ServiceObject:
    return ServiceObject(name=name, protocol=proto, dst_port=port)


def _existing_sched(name: str, end: str) -> ScheduleObject:
    return ScheduleObject(name=name, schedule_type="onetime", end_date=end)


def _existing_policy(
    policy_id: str, src_zone: str, dst_zone: str,
    src_obj: str, dst_obj: str, svc_obj: str,
    action: str = "accept", enabled: bool = True,
) -> FirewallPolicy:
    """造一个最小可用的 FirewallPolicy.
    FirewallPolicy 只有 name/src_zone/dst_zone/src_addrs/dst_addrs/services/schedule/action/enabled
    9 个字段, 没有 *_values/_ports 字段.
    """
    return FirewallPolicy(
        policy_id=policy_id, name=policy_id,
        src_zone=src_zone, dst_zone=dst_zone,
        src_addrs=[src_obj], dst_addrs=[dst_obj], services=[svc_obj],
        schedule=None,
        action=action, enabled=enabled,
    )


# ============================================================
# 1. PushMode enum 包含 3 个值
# ============================================================

def test_push_mode_enum_has_three_modes():
    """PushMode 枚举必须包含 3 mode (重构.md §3 三 mode 隔离)"""
    assert PushMode.force_push.value == "force_push"
    assert PushMode.deduplicate.value == "deduplicate"
    assert PushMode.reuse_objects.value == "reuse_objects"


# ============================================================
# 2. force_push 模式: 整条 CREATED
# ============================================================

def test_matcher_force_push_always_created():
    """force_push: 整条必新建 (不查重)"""
    addrs = [_existing_addr("Obj-10.1.1.5", "10.1.1.5")]
    svcs = [_existing_svc("TCP-80", "tcp", "80")]
    existing_policy = _existing_policy(
        policy_id="P99", src_zone="trust", dst_zone="untrust",
        src_obj="Obj-10.1.1.5", dst_obj="Obj-192.168.1.1", svc_obj="TCP-80",
    )

    matcher = PolicyMatcher(
        mode="force_push",
        existing_addresses=addrs, existing_services=svcs,
        existing_schedules=[], existing_policies=[existing_policy],
    )
    result = matcher.match_one(
        src_ips=["10.1.1.5"], dst_ips=["192.168.1.1"],
        ports=["80"], valid_until="长期",
    )
    assert result.action == MatchAction.CREATED, "force_push 应该返回 CREATED, 不查重"


# ============================================================
# 3. reuse_objects 模式: 整条 CREATED (跟 force_push 当前一致)
# ============================================================

def test_matcher_reuse_objects_always_created():
    """reuse_objects: 整条必新建, 对象复用 (跟 force_push 当前行为一致)"""
    addrs = [_existing_addr("Obj-10.1.1.5", "10.1.1.5/32")]  # value 配 /32 跟 _norm_ip 一致
    svcs = [_existing_svc("TCP-80", "tcp", "80")]
    existing_policy = _existing_policy(
        policy_id="P99", src_zone="trust", dst_zone="untrust",
        src_obj="Obj-10.1.1.5", dst_obj="Obj-192.168.1.1", svc_obj="TCP-80",
    )

    matcher = PolicyMatcher(
        mode="reuse_objects",
        existing_addresses=addrs, existing_services=svcs,
        existing_schedules=[], existing_policies=[existing_policy],
    )
    result = matcher.match_one(
        src_ips=["10.1.1.5"], dst_ips=["192.168.1.1"],
        ports=["80"], valid_until="长期",
    )
    assert result.action == MatchAction.CREATED, "reuse_objects 整条必新建 (跟 force_push 一致)"
    # ObjectReuse 字段应有复用对象名
    assert "Obj-10.1.1.5" in result.reuse.src_addrs, "reuse_objects 模式下对象应复用"


# ============================================================
# 4. deduplicate 模式: 命中 → REUSED
# ============================================================

def test_matcher_deduplicate_hit_returns_reused():
    """deduplicate: 4 维 HASH 命中 → REUSED (整条跳过)"""
    addrs = [
        _existing_addr("Obj-10.1.1.5", "10.1.1.5/32"),
        _existing_addr("Obj-192.168.1.1", "192.168.1.1/32"),
    ]
    svcs = [_existing_svc("TCP-80", "tcp", "80")]
    existing_policy = _existing_policy(
        policy_id="P99", src_zone="trust", dst_zone="untrust",
        src_obj="Obj-10.1.1.5", dst_obj="Obj-192.168.1.1", svc_obj="TCP-80",
    )

    matcher = PolicyMatcher(
        mode="deduplicate",
        existing_addresses=addrs, existing_services=svcs,
        existing_schedules=[], existing_policies=[existing_policy],
    )
    result = matcher.match_one(
        src_ips=["10.1.1.5"], dst_ips=["192.168.1.1"],
        ports=["80"], valid_until="长期",
        src_zone="trust", dst_zone="untrust",
    )
    assert result.action == MatchAction.REUSED, "4 维 HASH 命中应返回 REUSED"
    assert result.existing_device_policy_id == "P99"


# ============================================================
# 5. deduplicate 模式: 未命中 → CREATED
# ============================================================

def test_matcher_deduplicate_miss_returns_created():
    """deduplicate: 4 维 HASH 不命中 → CREATED"""
    addrs = [_existing_addr("Obj-Other", "10.99.99.1")]
    svcs = [_existing_svc("Other-TCP", "tcp", "9999")]
    existing_policy = _existing_policy(
        policy_id="P99", src_zone="trust", dst_zone="untrust",
        src_obj="Obj-Other", dst_obj="Obj-Other", svc_obj="Other-TCP",
    )

    matcher = PolicyMatcher(
        mode="deduplicate",
        existing_addresses=addrs, existing_services=svcs,
        existing_schedules=[], existing_policies=[existing_policy],
    )
    result = matcher.match_one(
        src_ips=["10.1.1.5"], dst_ips=["192.168.1.1"],
        ports=["80"], valid_until="长期",
    )
    assert result.action == MatchAction.CREATED, "未命中应返回 CREATED"


# ============================================================
# 6. 3 mode 互不干扰: 同一输入, 不同 mode 出不同结果
# ============================================================

def test_three_modes_isolated_with_same_input():
    """同一策略, 3 mode 出不同结果 (互不干扰)"""
    addrs = [
        _existing_addr("Obj-10.1.1.5", "10.1.1.5/32"),
        _existing_addr("Obj-192.168.1.1", "192.168.1.1/32"),
    ]
    svcs = [_existing_svc("TCP-80", "tcp", "80")]
    existing_policy = _existing_policy(
        policy_id="P99", src_zone="trust", dst_zone="untrust",
        src_obj="Obj-10.1.1.5", dst_obj="Obj-192.168.1.1", svc_obj="TCP-80",
    )

    kwargs = dict(
        src_ips=["10.1.1.5"], dst_ips=["192.168.1.1"],
        ports=["80"], valid_until="长期",
        src_zone="trust", dst_zone="untrust",
    )

    r_force = PolicyMatcher("force_push", addrs, svcs, [], [existing_policy]).match_one(**kwargs)
    r_reuse = PolicyMatcher("reuse_objects", addrs, svcs, [], [existing_policy]).match_one(**kwargs)
    r_dedup = PolicyMatcher("deduplicate", addrs, svcs, [], [existing_policy]).match_one(**kwargs)

    # force_push + reuse_objects 整条都 CREATED, deduplicate 命中 REUSED
    assert r_force.action == MatchAction.CREATED
    assert r_reuse.action == MatchAction.CREATED
    assert r_dedup.action == MatchAction.REUSED

    # 3 个的 match_key 应该相同 (跟 mode 无关, 都是 4 维 HASH)
    assert r_force.match_key == r_reuse.match_key == r_dedup.match_key


# ============================================================
# 7. PushPipeline 接受 3 mode
# ============================================================

def test_push_pipeline_accepts_three_modes():
    """PushPipeline.__init__ 接受 force_push / reuse_objects / deduplicate"""
    from app.services.push_pipeline import PushPipeline

    # 合法
    for m in ("force_push", "reuse_objects", "deduplicate"):
        p = PushPipeline(order_id=1, firewall_id=1, mode=m)
        assert p.mode == m

    # 非法
    with pytest.raises(ValueError, match="mode 必须是"):
        PushPipeline(order_id=1, firewall_id=1, mode="invalid_mode_xxx")


# ============================================================
# 8. push.py API 接受 reuse_objects
# ============================================================

def test_push_api_accepts_reuse_objects():
    """push API start_push_v2 接受 reuse_objects mode (HTTP 422 / 400 验证由 FastAPI 跑时测)"""
    # 静态检查: 文档字符串 + enum 已包含
    assert "reuse_objects" in {m.value for m in PushMode}
