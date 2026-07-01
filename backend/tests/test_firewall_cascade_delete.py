"""
测试 firewall DELETE 级联清理 4 张 FK 关联表

背景 (2026-06-22 bug):
  之前 delete_firewall 只删 Policy 表, 但还有 3 张表有 FK -> firewalls.id:
    - firewall_zones (fw 的安全域配置)
    - zone_access_configs (fw 的跨区 NAT 配置)
    - pushed_policy_snapshots (推送历史快照)
      - pushed_policy_items (快照内的策略条目, FK -> snapshot)
  结果: 删 firewall 时 psycopg2.ForeignKeyViolation 500 报错。

铁律: 4 张表必须先全删, 才能删 firewall 本身。
"""
import pytest
from app.models import (
    Firewall, FirewallZone, ZoneAccessConfig, Policy,
    PushedPolicySnapshot, PushedPolicyItem, PushLog,
    FirewallType, ConnectionType, Order, OrderStatus,
    PushMode, PushLogLevel,
)


@pytest.fixture
def fw_with_all_relations(db_session):
    """造一个 firewall + 4 张 FK 表都有数据, 准备被级联删"""
    fw = Firewall(
        name='fw-cascade-test',
        alias='级联删除测试',
        type=FirewallType.fortigate,
        management_ip='10.99.99.99',
        belong_region='测试区',
        connection_type=ConnectionType.ssh,
        is_zone_boundary=1,
        auto_push=0,
    )
    db_session.add(fw)
    db_session.commit()
    db_session.refresh(fw)

    # 1. ZoneAccessConfig
    cfg = ZoneAccessConfig(
        firewall_id=fw.id,
        source_region='生产区',
        dest_region='测试区',
        boundary_source_zone='DMZ',
        boundary_dest_zone='内网',
        need_nat=1,
        snat_pool='172.16.99.1',
    )
    db_session.add(cfg)

    # 2. FirewallZone
    zone = FirewallZone(
        firewall_id=fw.id,
        zone_name='内网',
        protected_ips='10.0.0.0/8',
        connect_region='测试区',
    )
    db_session.add(zone)

    # 3. Policy + Order
    order = Order(
        order_no='CASCADE-001',
        title='级联测试工单',
        description='pytest',
        status=OrderStatus.pending,
        excel_file_path='/tmp/fake.xlsx',
    )
    db_session.add(order)
    db_session.commit()
    policy = Policy(
        order_id=order.id,
        source_system_name='内网',
        source_ip='10.1.1.0/24',
        dest_system_name='DMZ',
        dest_ip='192.168.1.10',
        service='443',
        firewall_id=fw.id,
        device_source_zone='trust',      # spec §13 NOT NULL
        device_dest_zone='untrust',       # spec §13 NOT NULL
    )
    db_session.add(policy)

    # 4. PushedPolicySnapshot + PushedPolicyItem
    db_session.commit()
    snap = PushedPolicySnapshot(
        firewall_id=fw.id,
        order_id=order.id,
        batch_id='test-batch-001',         # spec NOT NULL
        push_mode=PushMode.deduplicate,    # spec NOT NULL
    )
    db_session.add(snap)
    db_session.commit()
    db_session.refresh(snap)
    item = PushedPolicyItem(
        snapshot_id=snap.id,
        policy_id=policy.id,
        match_key='test-match-key',
    )
    db_session.add(item)

    # 5. PushLog (snapshot 的子表, FK -> pushed_policy_snapshots.id)
    log = PushLog(
        snapshot_id=snap.id,
        seq=1,
        stage='connect',
        level=PushLogLevel.info,
        message='cascade test log',
    )
    db_session.add(log)
    db_session.commit()
    return fw


def test_delete_firewall_cascades_all_fk_tables(client, db_session, fw_with_all_relations):
    """删 firewall 时必须清光 5 张 FK 表

    5 张关联表 (FK 拓扑):
      - firewall_zones (fw.id 直接)
      - zone_access_configs (fw.id 直接)
      - policies (fw.id 直接)
      - pushed_policy_snapshots (fw.id 直接)
        - pushed_policy_items (snapshot_id)
        - push_logs (snapshot_id)
    """
    fw_id = fw_with_all_relations.id

    # 确认 5 张表都有数据
    assert db_session.query(Policy).filter(Policy.firewall_id == fw_id).count() == 1
    assert db_session.query(FirewallZone).filter(FirewallZone.firewall_id == fw_id).count() == 1
    assert db_session.query(ZoneAccessConfig).filter(ZoneAccessConfig.firewall_id == fw_id).count() == 1
    snaps = db_session.query(PushedPolicySnapshot).filter(PushedPolicySnapshot.firewall_id == fw_id).all()
    assert len(snaps) == 1
    snap_id = snaps[0].id
    assert db_session.query(PushedPolicyItem).filter(PushedPolicyItem.snapshot_id == snap_id).count() == 1
    assert db_session.query(PushLog).filter(PushLog.snapshot_id == snap_id).count() == 1

    # DELETE
    resp = client.delete(f'/api/firewalls/{fw_id}')
    assert resp.status_code == 204, f'删除应成功, 实际 {resp.status_code}: {resp.text}'

    # 验证 firewall 没了
    assert db_session.query(Firewall).filter(Firewall.id == fw_id).first() is None

    # 验证 5 张 FK 表全清
    assert db_session.query(Policy).filter(Policy.firewall_id == fw_id).count() == 0
    assert db_session.query(FirewallZone).filter(FirewallZone.firewall_id == fw_id).count() == 0
    assert db_session.query(ZoneAccessConfig).filter(ZoneAccessConfig.firewall_id == fw_id).count() == 0
    assert db_session.query(PushedPolicySnapshot).filter(PushedPolicySnapshot.firewall_id == fw_id).count() == 0
    assert db_session.query(PushedPolicyItem).filter(PushedPolicyItem.snapshot_id == snap_id).count() == 0
    assert db_session.query(PushLog).filter(PushLog.snapshot_id == snap_id).count() == 0


def test_delete_firewall_404_when_missing(client, db_session):
    """删不存在的 firewall 应返 404, 不 500"""
    resp = client.delete('/api/firewalls/99999')
    assert resp.status_code == 404


def test_delete_firewall_with_only_zones(client, db_session):
    """只配 zones 没推过策略的防火墙也能删"""
    fw = Firewall(
        name='fw-only-zones',
        type=FirewallType.huawei,
        management_ip='10.99.99.50',
        belong_region='测试区',
        connection_type=ConnectionType.ssh,
        is_zone_boundary=0,
        auto_push=0,
    )
    db_session.add(fw)
    db_session.commit()
    db_session.refresh(fw)

    zone = FirewallZone(
        firewall_id=fw.id,
        zone_name='trust',
        protected_ips='10.0.0.0/8',
        connect_region='测试区',
    )
    db_session.add(zone)
    db_session.commit()

    resp = client.delete(f'/api/firewalls/{fw.id}')
    assert resp.status_code == 204
    assert db_session.query(FirewallZone).filter(FirewallZone.firewall_id == fw.id).count() == 0
