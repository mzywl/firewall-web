"""
测试 chain_planner (统一寻路入口)

覆盖 D 方案 Pass 1+Pass 2 级联匹配的所有关键场景:
  - 单防火墙同区 (出向)
  - 跨区 boundary + SNAT (边界墙)
  - 3 墙级联 (Pass 2 SNAT 透传)
  - (direction, src 归属) 二元判定 (坑点 33 回归)
  - unmatched (src 不在任何 boundary 范围)
  - boundary 缺 SNAT 池
  - 同防火墙不允许推送
  - user_modified 快照使用时间透传
  - 异常 IP 容错
"""
import pytest
from app.core.chain_planner import ChainPlanner, ChainContext, _find_boundary_fw_for_src
from app.models import (
    Firewall, Policy, Order, OrderStatus, FirewallType, ConnectionType,
    ZoneAccessConfig,
)


# ============================================================
# 工厂 fixtures: 造多防火墙拓扑 (1 boundary + 1 后游)
# ============================================================

@pytest.fixture
def boundary_fw(db_session):
    """边界防火墙 fw6-like: 测试区, outbound_snat_pool='10.223.32.1'
    只配 internal 段 (避免 src 误判为 inbound SNAT 透传, 本测试聚焦 outbound + Pass 2)
    """
    fw = Firewall(
        name='fw-boundary',
        alias='边界墙',
        type=FirewallType.fortigate,
        management_ip='10.99.99.6',
        region='测试区',
        covered_region='测试区',
        local_zone_name='Trust',
        external_zone_name='Untrust',
        connection_type=ConnectionType.ssh,
        internal_protected_ips='192.101.64.0/24\n192.101.66.0/24',
        external_protected_ips='203.0.113.0/24',  # 跟下游 external 不重叠, 避免误判
        is_zone_boundary=1,
        auto_push=0,
        outbound_snat_pool='10.223.32.1',
    )
    db_session.add(fw)
    db_session.commit()
    db_session.refresh(fw)
    return fw


@pytest.fixture
def downstream_fw(db_session):
    """后游防火墙 fw14-like: 生产区, non-boundary, 物理上看到的是 SNAT 后 src.
    external 段不含 boundary.internal 段 (192.101.64.0/24), 避免直连 inbound 误判为 inbound SNAT 透传.
    """
    fw = Firewall(
        name='fw-downstream',
        alias='后游墙',
        type=FirewallType.h3c,
        management_ip='10.99.99.14',
        region='生产区',
        covered_region='生产区',
        local_zone_name='Trust',
        external_zone_name='Untrust',
        connection_type=ConnectionType.ssh,
        internal_protected_ips='10.2.179.0/24',
        external_protected_ips='10.0.0.0/8',  # 不含 192.101.64.0/24
        is_zone_boundary=0,
        auto_push=0,
    )
    db_session.add(fw)
    db_session.commit()
    db_session.refresh(fw)
    return fw


@pytest.fixture
def same_region_fw(db_session):
    """同区防火墙 (fw7-like): 测试区, non-boundary, 跟 boundary_fw 同 region.
    跟 boundary.internal 段不重叠, 避免 splitter 把它当 boundary 下游.
    """
    fw = Firewall(
        name='fw-same-region',
        alias='同区墙',
        type=FirewallType.h3c,
        management_ip='10.99.99.7',
        region='测试区',
        covered_region='测试区',
        local_zone_name='Trust',
        external_zone_name='Untrust',
        connection_type=ConnectionType.ssh,
        internal_protected_ips='172.16.0.0/16',  # 跟 boundary 不重叠
        external_protected_ips='10.0.0.0/8',
        is_zone_boundary=0,
        auto_push=0,
    )
    db_session.add(fw)
    db_session.commit()
    db_session.refresh(fw)
    return fw


def _make_order(db_session, order_no='TEST-CHAIN-001'):
    order = Order(
        order_no=order_no,
        title='chain_planner 测试工单',
        description='pytest',
        status=OrderStatus.pending,
        excel_file_path='/tmp/fake.xlsx',
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def _make_policy(db_session, order_id, **kwargs):
    defaults = dict(
        order_id=order_id,
        firewall_id=None,
        source_system_name='生产区',
        source_ip='10.1.1.0/24',
        dest_system_name='测试区',
        dest_ip='192.168.1.10',
        service='443',
        action='permit',
    )
    defaults.update(kwargs)
    p = Policy(**defaults)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _make_zone_cfg(db_session, firewall_id, src, dst):
    cfg = ZoneAccessConfig(
        firewall_id=firewall_id, source_zone=src, dest_zone=dst, description='test'
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


# ============================================================
# 1. 单防火墙同区 (出向)
# ============================================================

def test_chain_planner_outbound_same_firewall(
    db_session, sample_firewall, sample_policy
):
    """policy.src ∈ fw.internal, dst ∈ fw.external → 边界墙做 SNAT"""
    planner = ChainPlanner(db_session)
    ctx = planner.generate_chain_execution_plan([sample_policy], {})

    # 边界墙 fw-test 应该上墙 + SNAT 转换
    assert sample_firewall.id in ctx.firewall_groups
    group = ctx.firewall_groups[sample_firewall.id]
    assert len(group['policies']) == 1
    p = group['policies'][0]
    # 铁律: 边界墙自己用原始 src 上墙 (策略匹配在 SNAT 前)
    # splitter 拆 CIDR 时保留 '10.1.1.0/24' (host 拆成 '10.1.1.1')
    assert p['source_ip'] in ('10.1.1.0/24', '10.1.1.1')
    assert p['direction'] == 'outbound'
    assert p['nat_info']['need_nat'] is True
    assert p['nat_info']['nat_type'] == 'SNAT'


# ============================================================
# 2. 跨区 + boundary + SNAT 转换登记
# ============================================================

def test_chain_planner_boundary_snat_registers_target_region(
    db_session, boundary_fw, downstream_fw, same_region_fw
):
    """boundary_fw 做 SNAT 时, 应登记 boundary_snat_map[target_region]"""
    order = _make_order(db_session)
    _make_zone_cfg(db_session, boundary_fw.id, '生产区', '测试区')
    # 跨区策略: src 在生产区 (boundary 后面), dst 在测试区
    p = _make_policy(
        db_session, order.id,
        source_ip='192.101.64.2',  # 在 boundary_fw.internal 内
        dest_ip='10.2.179.130',    # 在 downstream_fw.internal 内
    )

    planner = ChainPlanner(db_session)
    ctx = planner.generate_chain_execution_plan([p], {})

    # boundary_snat_map 应有登记
    assert len(ctx.boundary_snat_map) >= 1
    # 出向 SNAT, target_region 应是 cfg.dest_zone = '测试区'
    snat_entry = list(ctx.boundary_snat_map.values())[0]
    assert snat_entry['translated_src_ip'] == '10.223.32.1'
    assert snat_entry['firewall_id'] == boundary_fw.id


# ============================================================
# 3. 3 墙级联 (D 方案核心): boundary → 下游
# ============================================================

def test_chain_planner_cascade_downstream_inbound_pass2(
    db_session, boundary_fw, downstream_fw, same_region_fw
):
    """
    跨区 + 3 墙级联:
      - boundary_fw: src=192.101.64.2 (boundary internal) → 出向 + SNAT 登记
      - downstream_fw: src=10.1.137.137 (直连, 不在 boundary 范围) → 直连 inbound
      - downstream_fw: src=192.101.64.2 (boundary internal 命中) → Pass 2 替换成 SNAT 后 IP
    """
    order = _make_order(db_session, 'TEST-CASCADE-001')
    _make_zone_cfg(db_session, boundary_fw.id, '生产区', '测试区')
    # src 含 2 个 IP: 一个直连 (10.1.137.137) + 一个 boundary SNAT 后的产物 (192.101.64.2)
    p = _make_policy(
        db_session, order.id,
        source_ip='10.1.137.137\n192.101.64.2',
        dest_ip='10.2.179.130',
    )

    planner = ChainPlanner(db_session)
    ctx = planner.generate_chain_execution_plan([p], {p.id: '长期'})

    # boundary_fw 应有 1 条 sp (原始 src)
    assert boundary_fw.id in ctx.firewall_groups
    boundary_policies = ctx.firewall_groups[boundary_fw.id]['policies']
    assert len(boundary_policies) == 1
    # 铁律: boundary 自己用原始 src
    assert boundary_policies[0]['source_ip'] == '192.101.64.2'
    assert boundary_policies[0]['nat_info']['nat_type'] == 'SNAT'

    # downstream_fw 应有 2 条 sp:
    #   sp1 (10.1.137.137): 直连 inbound
    #   sp2 (192.101.64.2): Pass 2 替换成 SNAT 后 IP (10.223.32.1)
    assert downstream_fw.id in ctx.firewall_groups
    downstream_policies = ctx.firewall_groups[downstream_fw.id]['policies']
    assert len(downstream_policies) == 2

    src_ips = sorted(p['source_ip'] for p in downstream_policies)
    assert '10.1.137.137' in src_ips
    assert '10.223.32.1' in src_ips  # Pass 2 替换生效

    # sp2 应有 snat_address + via_firewall 标识 (D 方案 SNAT 透传)
    snat_sp = next(p for p in downstream_policies if p['source_ip'] == '10.223.32.1')
    assert snat_sp['nat_info']['snat_address'] == '10.223.32.1'
    assert snat_sp['nat_info']['via_firewall']['id'] == boundary_fw.id
    assert snat_sp['nat_info']['need_nat'] is False
    assert snat_sp['nat_info']['nat_type'] is None

    # 直连 sp 应保持原始 src, 无 SNAT 透传标识
    direct_sp = next(p for p in downstream_policies if p['source_ip'] == '10.1.137.137')
    assert direct_sp['nat_info'].get('snat_address') is None
    assert direct_sp['nat_info'].get('via_firewall') is None


# ============================================================
# 4. 坑点 33 回归: outbound 方向不做 SNAT 替换
# ============================================================

def test_chain_planner_outbound_not_replaced_by_pass2(
    db_session, boundary_fw, same_region_fw
):
    """
    关键回归: same_region_fw 是 boundary_fw 的同区物理拓扑伙伴,
    如果 same_region_fw 自己出向 (src 在其 internal), 不能用 Pass 2 替换成 SNAT 后 IP

    物理上: same_region_fw 看到的 src 是原始 (SNAT 还没发生)
    错误实现: 误把 same_region_fw 当 boundary_fw 下游 → src 被替换成 10.223.32.1
    """
    order = _make_order(db_session, 'TEST-OUTBOUND-NOREPLACE')
    _make_zone_cfg(db_session, boundary_fw.id, '生产区', '测试区')
    # same_region_fw: internal=172.16.0.0/16, 用 172.16.5.5 触发 outbound
    # dst=8.8.8.8 不在 same_region_fw 任何段 → splitter 算 outbound
    p = _make_policy(
        db_session, order.id,
        source_ip='172.16.5.5',
        dest_ip='8.8.8.8',
    )

    planner = ChainPlanner(db_session)
    ctx = planner.generate_chain_execution_plan([p], {})

    # same_region_fw 应该直接上墙, src 保持原始 (172.16.5.5), 不被替换
    assert same_region_fw.id in ctx.firewall_groups
    sp = ctx.firewall_groups[same_region_fw.id]['policies'][0]
    assert sp['source_ip'] == '172.16.5.5'  # 原始, 不替换
    assert sp['direction'] == 'outbound'
    assert sp['nat_info'].get('snat_address') is None  # 无 SNAT 透传


# ============================================================
# 5. unmatched: src 不在任何 boundary 管辖范围
# ============================================================

def test_chain_planner_inbound_src_not_in_any_boundary(
    db_session, downstream_fw
):
    """
    下游 fw inbound + src 不在任何 boundary 管辖范围 → 直连上墙
    (2026-06-21 修: 之前误判 unmatched, 实际是直连 client 访问, 应该上墙 src 保持原始)

    铁律兼容: 防火墙只认当前进到接口的包, 直连 src 没经过 NAT, 物理上就是原始 IP
    """
    order = _make_order(db_session, 'TEST-DIRECT-INBOUND')
    p = _make_policy(
        db_session, order.id,
        source_ip='8.8.8.8',  # 不在任何 boundary 内, 直连
        dest_ip='10.2.179.130',  # 在 downstream_fw.internal
    )

    planner = ChainPlanner(db_session)
    ctx = planner.generate_chain_execution_plan([p], {})

    # downstream_fw 应直连上墙, src 保持原始 (8.8.8.8)
    assert downstream_fw.id in ctx.firewall_groups
    assert len(ctx.firewall_groups[downstream_fw.id]['policies']) == 1
    sp = ctx.firewall_groups[downstream_fw.id]['policies'][0]
    assert sp['source_ip'] == '8.8.8.8'
    assert sp['direction'] == 'inbound'
    assert sp['nat_info'].get('snat_address') is None  # 直连, 无 SNAT 透传
    # 不应进 unmatched
    assert len(ctx.not_pushed) == 0


# ============================================================
# 6. boundary 缺 SNAT 池
# ============================================================

def test_chain_planner_boundary_without_snat_pool(
    db_session, sample_firewall
):
    """boundary 触发 SNAT 但没配 snat_pool → nat_type=None + warning"""
    # 把 sample_firewall 的 snat_pool 清空
    sample_firewall.outbound_snat_pool = None
    sample_firewall.inbound_snat_pool = None
    db_session.commit()

    order = _make_order(db_session, 'TEST-NO-SNAT-POOL')
    p = _make_policy(
        db_session, order.id,
        source_ip='10.0.0.5',  # 在 sample_firewall.internal
        dest_ip='192.168.1.10',  # 在 sample_firewall.external
    )

    planner = ChainPlanner(db_session)
    ctx = planner.generate_chain_execution_plan([p], {})

    # 仍然上墙, 但 nat_type=None + warning
    assert sample_firewall.id in ctx.firewall_groups
    p = ctx.firewall_groups[sample_firewall.id]['policies'][0]
    assert p['nat_info']['need_nat'] is True  # 仍然判定要 NAT
    assert p['nat_info']['nat_type'] is None  # 但池空, 类型降级
    assert any('SNAT 地址池未配置' in w for w in ctx.warnings)


# ============================================================
# 7. 同防火墙不允许推送 (默认)
# ============================================================

def test_chain_planner_same_firewall_disabled_by_default(
    db_session, sample_firewall
):
    """
    源目的 IP 都在 sample_firewall 内部, allow_same_firewall_push=0 → unmatched
    """
    order = _make_order(db_session, 'TEST-SAME-FW-DISABLED')
    p = _make_policy(
        db_session, order.id,
        source_ip='10.0.0.5',  # 在 sample_firewall.internal (10.0.0.0/8)
        dest_ip='10.0.0.6',    # 也在 sample_firewall.internal
    )

    planner = ChainPlanner(db_session)
    ctx = planner.generate_chain_execution_plan([p], {})

    # sample_firewall 不应在 policies 中
    if sample_firewall.id in ctx.firewall_groups:
        assert len(ctx.firewall_groups[sample_firewall.id]['policies']) == 0
    # 在 unmatched 列表 (splitter 内部 same_firewall 判定)
    assert len(ctx.not_pushed) == 1


# ============================================================
# 8. user_modified 快照使用时间透传
# ============================================================

def test_chain_planner_preserves_usage_time_from_snapshot(
    db_session, sample_firewall, sample_policy
):
    """使用时间应从 usage_time_by_id 透传到上墙的 sp"""
    planner = ChainPlanner(db_session)
    ctx = ChainPlanner(db_session).generate_chain_execution_plan(
        [sample_policy], {sample_policy.id: '2026-12-31'}
    )

    p = ctx.firewall_groups[sample_firewall.id]['policies'][0]
    assert p['使用时间'] == '2026-12-31'


# ============================================================
# 9. 异常 IP 输入容错
# ============================================================

def test_chain_planner_handles_invalid_ip_gracefully(
    db_session, sample_firewall
):
    """无效 IP 不应让整个 ChainPlanner 崩溃, 走 unmatched"""
    order = _make_order(db_session, 'TEST-INVALID-IP')
    p = _make_policy(
        db_session, order.id,
        source_ip='not-an-ip',
        dest_ip='192.168.1.10',
    )

    planner = ChainPlanner(db_session)
    # 不应抛异常
    ctx = planner.generate_chain_execution_plan([p], {})

    # splitter 内部已经处理非法 IP (not_pushed_reason), 应该在 unmatched
    assert len(ctx.not_pushed) >= 1


# ============================================================
# 10. _find_boundary_fw_for_src helper 单元测试
# ============================================================

def test_find_boundary_fw_for_src_hits_internal(
    db_session, boundary_fw, downstream_fw
):
    """src 在 boundary_fw.internal → 命中 (outbound SNAT)"""
    result = _find_boundary_fw_for_src('192.101.64.2', downstream_fw, db_session)
    assert result is not None
    assert result['boundary_fw'].id == boundary_fw.id
    assert result['direction'] == 'outbound'
    assert result['snat_pool'] == '10.223.32.1'


def test_find_boundary_fw_for_src_hits_external(
    db_session, boundary_fw, downstream_fw
):
    """src 在 boundary_fw.external → 命中 (inbound SNAT)
    boundary_fw.external 配的是 203.0.113.0/24, 用 203.0.113.5 触发
    """
    result = _find_boundary_fw_for_src('203.0.113.5', downstream_fw, db_session)
    assert result is not None
    assert result['boundary_fw'].id == boundary_fw.id
    assert result['direction'] == 'inbound'


def test_find_boundary_fw_for_src_returns_none_for_unrelated(
    db_session, boundary_fw, downstream_fw
):
    """src 不在任何 boundary 范围 → None"""
    result = _find_boundary_fw_for_src('8.8.8.8', downstream_fw, db_session)
    assert result is None


def test_find_boundary_fw_for_src_excludes_self(
    db_session, boundary_fw
):
    """helper 不会返回 current_fw 自己 (即使 current_fw 是 boundary)"""
    result = _find_boundary_fw_for_src('192.101.64.2', boundary_fw, db_session)
    assert result is None  # 排除自己


def test_find_boundary_fw_for_src_handles_invalid_input(
    db_session, boundary_fw, downstream_fw
):
    """非法 IP 输入 (FQDN, 乱码) 不抛异常, 返回 None"""
    # 这些都是 splitter 之外可能传进来的, helper 必须容错
    assert _find_boundary_fw_for_src('not-an-ip', downstream_fw, db_session) is None
    assert _find_boundary_fw_for_src('', downstream_fw, db_session) is None
    assert _find_boundary_fw_for_src('0.0.0.0', downstream_fw, db_session) is None
    assert _find_boundary_fw_for_src('any', downstream_fw, db_session) is None
    assert _find_boundary_fw_for_src('192.168.999.1', downstream_fw, db_session) is None
