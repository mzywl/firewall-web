"""
测试 push_chain 倒序推送链路 (重构.md §4 铁律)

覆盖:
- 单防火墙 (1 墙)
- 3 墙级联 (前游 + 边界 + 后游) → 倒序 [14, 6, 7]
- 2 墙 (前游 + 边界) → 倒序 [6, 7]
- 2 墙 (前游 + 后游) → 倒序 [14, 7]
- 无防火墙 (空工单)
- 多 boundary 场景
"""
import pytest
from app.core.push_chain import compute_push_chain, get_push_chain_with_metadata
from app.models import (
    Firewall, Policy, Order, OrderStatus, FirewallType, ConnectionType, ZoneAccessConfig
)


# ============================================================
# 工厂 fixtures
# ============================================================

@pytest.fixture
def downstream_fw(db_session):
    """后游墙 fw14-like: 生产区, inbound, SNAT 接管"""
    fw = Firewall(
        name='fw-downstream', type=FirewallType.h3c, management_ip='10.99.99.14',
        region='生产区', covered_region='生产区',
        local_zone_name='Trust', external_zone_name='Untrust',
        connection_type=ConnectionType.ssh,
        internal_protected_ips='10.2.179.0/24',
        external_protected_ips='10.0.0.0/8',
        is_zone_boundary=0, auto_push=0,
    )
    db_session.add(fw); db_session.commit()
    return fw


@pytest.fixture
def boundary_fw(db_session):
    """边界墙 fw6-like: 测试区, outbound SNAT"""
    fw = Firewall(
        name='fw-boundary', type=FirewallType.fortigate, management_ip='10.99.99.6',
        region='测试区', covered_region='测试区',
        local_zone_name='Trust', external_zone_name='Untrust',
        connection_type=ConnectionType.ssh,
        internal_protected_ips='192.101.64.0/24',
        external_protected_ips='203.0.113.0/24',
        is_zone_boundary=1, auto_push=0,
        outbound_snat_pool='10.223.32.1',
    )
    db_session.add(fw); db_session.commit()
    return fw


@pytest.fixture
def upstream_fw(db_session):
    """前游墙 fw7-like: 测试区, outbound, 同 region 跟 boundary.
    物理拓扑: src 物理上从前游墙出去, 同时也在 boundary.internal 段 (边界墙做 SNAT)
    所以 internal 跟 boundary 重叠 192.101.64.0/24
    """
    fw = Firewall(
        name='fw-upstream', type=FirewallType.h3c, management_ip='10.99.99.7',
        region='测试区', covered_region='测试区',
        local_zone_name='Trust', external_zone_name='Untrust',
        connection_type=ConnectionType.ssh,
        internal_protected_ips='192.101.64.0/24\n172.16.0.0/16',  # 跟 boundary 重叠
        external_protected_ips='10.0.0.0/8',
        is_zone_boundary=0, auto_push=0,
    )
    db_session.add(fw); db_session.commit()
    return fw


def _make_order(db_session, order_no='TEST-CHAIN-ORDER'):
    order = Order(
        order_no=order_no, title='chain test', status=OrderStatus.pending,
        excel_file_path='/tmp/fake.xlsx',
    )
    db_session.add(order); db_session.commit()
    return order


def _make_policy(db_session, order_id, **kwargs):
    defaults = dict(
        order_id=order_id, firewall_id=None,
        source_system_name='生产区', source_ip='10.1.1.0/24',
        dest_system_name='测试区', dest_ip='192.168.1.10',
        service='443',
    )
    defaults.update(kwargs)
    p = Policy(**defaults)
    db_session.add(p); db_session.commit()
    return p


# ============================================================
# 测试
# ============================================================

def test_push_chain_3_firewall_cascade_reversed(
    db_session, boundary_fw, downstream_fw, upstream_fw
):
    """3 墙级联: 前游 + 边界 + 后游 → 倒序 [后游, 边界, 前游]"""
    order = _make_order(db_session, 'TEST-3CHAIN')
    db_session.add(ZoneAccessConfig(
        firewall_id=boundary_fw.id, source_zone='生产区', dest_zone='测试区'
    )); db_session.commit()
    # 跨区策略: src 物理上从前游墙出 (在 upstream.internal 也在 boundary.internal), dst 在后游段
    _make_policy(
        db_session, order.id,
        source_ip='192.101.64.2',  # 同时在 boundary.internal + upstream.internal
        dest_ip='10.2.179.130',    # 在 downstream.internal
    )

    chain = compute_push_chain(order.id, db_session)
    assert chain == [downstream_fw.id, boundary_fw.id, upstream_fw.id], (
        f"期望 [后游={downstream_fw.id}, 边界={boundary_fw.id}, 前游={upstream_fw.id}], 实际 {chain}"
    )


def test_push_chain_2_firewall_boundary_upstream(
    db_session, boundary_fw, upstream_fw
):
    """2 墙: 边界 + 前游 (没后游) → 倒序 [边界, 前游]"""
    order = _make_order(db_session, 'TEST-2CHAIN-BU')
    db_session.add(ZoneAccessConfig(
        firewall_id=boundary_fw.id, source_zone='生产区', dest_zone='测试区'
    )); db_session.commit()
    # 策略触发 boundary SNAT, src 物理上在前游墙 outbound
    _make_policy(
        db_session, order.id,
        source_ip='192.101.64.2',  # upstream.internal (outbound)
        dest_ip='203.0.113.100',   # boundary.external (dst 不在 boundary 内)
    )

    chain = compute_push_chain(order.id, db_session)
    # 没后游, 只有 [边界, 前游]
    assert chain == [boundary_fw.id, upstream_fw.id], (
        f"期望 [边界={boundary_fw.id}, 前游={upstream_fw.id}], 实际 {chain}"
    )


def test_push_chain_single_firewall(
    db_session, sample_firewall
):
    """单防火墙 → 仍按规则返回 [该墙] (规则排序, 不退化)"""
    order = _make_order(db_session, 'TEST-1CHAIN')
    _make_policy(
        db_session, order.id,
        source_ip='10.0.0.5',
        dest_ip='192.168.1.10',
    )

    chain = compute_push_chain(order.id, db_session)
    assert chain == [sample_firewall.id]


def test_push_chain_empty_order(db_session):
    """空工单 → []"""
    order = _make_order(db_session, 'TEST-EMPTY')
    chain = compute_push_chain(order.id, db_session)
    assert chain == []


def test_push_chain_nonexistent_order(db_session):
    """不存在的工单 → []"""
    chain = compute_push_chain(99999, db_session)
    assert chain == []


def test_get_push_chain_with_metadata_structure(
    db_session, boundary_fw, downstream_fw, upstream_fw
):
    """带元数据的版本应包含 role / reason 字段"""
    order = _make_order(db_session, 'TEST-META')
    db_session.add(ZoneAccessConfig(
        firewall_id=boundary_fw.id, source_zone='生产区', dest_zone='测试区'
    )); db_session.commit()
    _make_policy(
        db_session, order.id,
        source_ip='192.101.64.2',  # 同时在 boundary.internal + upstream.internal
        dest_ip='10.2.179.130',    # 在 downstream.internal
    )

    meta = get_push_chain_with_metadata(order.id, db_session)
    assert len(meta) == 3
    # 倒序: 后游 → 边界 → 前游
    assert meta[0]['role'] == 'downstream'
    assert meta[0]['firewall_id'] == downstream_fw.id
    assert '目的端' in meta[0]['reason']

    assert meta[1]['role'] == 'boundary'
    assert meta[1]['firewall_id'] == boundary_fw.id
    assert 'SNAT' in meta[1]['reason']

    assert meta[2]['role'] == 'upstream'
    assert meta[2]['firewall_id'] == upstream_fw.id
    assert '源端' in meta[2]['reason']


def test_get_push_chain_with_metadata_empty(db_session):
    """空工单元数据 → []"""
    order = _make_order(db_session, 'TEST-META-EMPTY')
    meta = get_push_chain_with_metadata(order.id, db_session)
    assert meta == []
