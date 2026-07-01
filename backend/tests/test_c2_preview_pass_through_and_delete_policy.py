"""
测试 C2 改动:
  1. firewall-zones/all 聚合接口
  2. DELETE /workorders/{order_id}/policies/{policy_id} API function
"""
import json
import pytest
from app.models import (
    Firewall, Policy, Order, OrderStatus, PolicyVersion,
    FirewallType, ConnectionType,
)
from app.api.orders import delete_order_policy
from app.api.firewall_zones import get_all_firewall_zones
from app.database import get_db
from fastapi import HTTPException


# ============================================================
# 1. firewall-zones/all 聚合
# ============================================================

def test_firewall_zones_all_aggregates_count(client, db_session):
    """聚合接口按 firewall_id 返回 zone 数"""
    fw1 = Firewall(
        name='fw-z1', type=FirewallType.fortigate, management_ip='10.0.0.1',
        belong_region='测试区', connection_type=ConnectionType.ssh,
        is_zone_boundary=1, auto_push=0,
    )
    fw2 = Firewall(
        name='fw-z2', type=FirewallType.huawei, management_ip='10.0.0.2',
        belong_region='生产区', connection_type=ConnectionType.ssh,
        is_zone_boundary=0, auto_push=0,
    )
    db_session.add_all([fw1, fw2])
    db_session.commit()

    from app.models import FirewallZone
    for i in range(3):
        db_session.add(FirewallZone(firewall_id=fw1.id, zone_name=f'z{i}',
                                     protected_ips='10.0.0.0/8', connect_region='测试区'))
    db_session.add(FirewallZone(firewall_id=fw2.id, zone_name='trust',
                                 protected_ips='192.168.0.0/16', connect_region='生产区'))
    db_session.commit()

    resp = client.get('/api/firewall-zones/all')
    assert resp.status_code == 200
    data = resp.json()
    mapping = {row['firewall_id']: row['zone_count'] for row in data['firewall_zones']}

    assert mapping.get(fw1.id) == 3
    assert mapping.get(fw2.id) == 1


# ============================================================
# 2. DELETE policy - 直接调 API function (避免 SQLite session 共享陷阱)
# ============================================================

@pytest.fixture
def order_with_policies(db_session):
    """造一个工单 + 3 条策略 + user_modified 快照"""
    order = Order(
        order_no='DEL-001', title='删除测试', description='pytest',
        status=OrderStatus.pending, excel_file_path='/tmp/fake.xlsx',
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    fw = Firewall(
        name='fw-del-test', type=FirewallType.fortigate, management_ip='10.99.99.1',
        belong_region='测试区', connection_type=ConnectionType.ssh,
        is_zone_boundary=1, auto_push=0,
    )
    db_session.add(fw)
    db_session.commit()
    db_session.refresh(fw)

    policies = []
    for i in range(3):
        p = Policy(
            order_id=order.id, source_system_name=f'系统A{i}',
            source_ip=f'10.1.{i}.0/24',
            dest_system_name=f'系统B{i}', dest_ip=f'10.2.{i}.10',
            service='443', firewall_id=fw.id,
            device_source_zone='trust', device_dest_zone='untrust',
        )
        db_session.add(p)
        policies.append(p)
    db_session.commit()

    snap_data = {
        "policies": [
            {"id": p.id, "使用时间": "长期"} for p in policies
        ]
    }
    snap = PolicyVersion(
        order_id=order.id, version_type='user_modified', data=snap_data,
    )
    db_session.add(snap)
    db_session.commit()

    return order, policies


def test_delete_order_policy_removes_from_policy_table(db_session, order_with_policies):
    """删 Policy 表条目"""
    order, policies = order_with_policies
    target = policies[1]

    result = delete_order_policy(order_id=order.id, policy_id=target.id, db=db_session)
    assert result is None  # 204 返回 None

    db_session.expire_all()
    assert db_session.query(Policy).filter(Policy.id == target.id).first() is None
    assert db_session.query(Policy).filter(Policy.order_id == order.id).count() == 2


def test_delete_order_policy_clears_user_modified_snapshot(db_session, order_with_policies):
    """删 Policy 时同步清 user_modified 快照里的对应条目"""
    order, policies = order_with_policies
    target = policies[0]

    delete_order_policy(order_id=order.id, policy_id=target.id, db=db_session)

    db_session.expire_all()
    snap = db_session.query(PolicyVersion).filter(
        PolicyVersion.order_id == order.id,
        PolicyVersion.version_type == 'user_modified',
    ).first()
    snap_ids = [p['id'] for p in snap.data['policies']]
    assert target.id not in snap_ids, 'user_modified 快照应同步清理'
    assert len(snap_ids) == 2, '3 - 1 = 2 条'


def test_delete_order_policy_404_when_missing(db_session, order_with_policies):
    """删不存在的策略应抛 404"""
    order, _ = order_with_policies
    with pytest.raises(HTTPException) as exc_info:
        delete_order_policy(order_id=order.id, policy_id=99999, db=db_session)
    assert exc_info.value.status_code == 404


def test_delete_order_policy_404_when_order_missing(db_session):
    """工单不存在应抛 404"""
    with pytest.raises(HTTPException) as exc_info:
        delete_order_policy(order_id=99999, policy_id=1, db=db_session)
    assert exc_info.value.status_code == 404


def test_delete_order_policy_wrong_order_404(db_session, order_with_policies):
    """policy 不属于该 order 应抛 404 (跨工单防误删)"""
    order, policies = order_with_policies
    target = policies[0]

    other_order = Order(
        order_no='OTHER-001', title='其他', description='pytest',
        status=OrderStatus.pending, excel_file_path='/tmp/fake.xlsx',
    )
    db_session.add(other_order)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_order_policy(order_id=other_order.id, policy_id=target.id, db=db_session)
    assert exc_info.value.status_code == 404
