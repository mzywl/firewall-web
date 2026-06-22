"""
测试 GET /api/zone-access/firewalls 只返 is_zone_boundary=1 的防火墙

背景 (2026-06-22 UX 需求):
  zone-access 全局视图是跨区 NAT 配置, 非边界墙做不了,
  让用户看不到非边界墙更直观。
  注: 全局防火墙列表 GET /api/firewalls 不受此过滤限制。
"""
import pytest
from app.models import Firewall, FirewallType, ConnectionType


@pytest.fixture
def mixed_firewalls(db_session):
    """造 1 边界墙 + 1 非边界墙"""
    boundary_fw = Firewall(
        name='fw-boundary',
        type=FirewallType.fortigate,
        management_ip='10.99.1.1',
        belong_region='生产区',
        connection_type=ConnectionType.ssh,
        is_zone_boundary=1,
        auto_push=0,
    )
    non_boundary_fw = Firewall(
        name='fw-non-boundary',
        type=FirewallType.huawei,
        management_ip='10.99.2.1',
        belong_region='生产区',
        connection_type=ConnectionType.ssh,
        is_zone_boundary=0,
        auto_push=0,
    )
    db_session.add(boundary_fw)
    db_session.add(non_boundary_fw)
    db_session.commit()
    return boundary_fw, non_boundary_fw


def test_zone_access_firewalls_only_returns_boundary(client, mixed_firewalls):
    """zone-access API 只返 is_zone_boundary=1 的防火墙"""
    boundary_fw, non_boundary_fw = mixed_firewalls

    resp = client.get('/api/zone-access/firewalls')
    assert resp.status_code == 200
    data = resp.json()
    ids = [fw['id'] for fw in data['firewalls']]

    assert boundary_fw.id in ids, '边界墙应在列表'
    assert non_boundary_fw.id not in ids, '非边界墙应被过滤'


def test_zone_access_firewalls_excludes_inactive(client, db_session):
    """is_active=0 的防火墙也应被过滤 (历史行为保留)"""
    inactive_fw = Firewall(
        name='fw-inactive',
        type=FirewallType.fortigate,
        management_ip='10.99.3.1',
        belong_region='生产区',
        connection_type=ConnectionType.ssh,
        is_zone_boundary=1,
        is_active=0,
        auto_push=0,
    )
    db_session.add(inactive_fw)
    db_session.commit()

    resp = client.get('/api/zone-access/firewalls')
    data = resp.json()
    ids = [fw['id'] for fw in data['firewalls']]

    assert inactive_fw.id not in ids, '禁用防火墙应被过滤'


def test_zone_access_firewalls_includes_is_zone_boundary_field(client, mixed_firewalls):
    """响应里应带 is_zone_boundary 字段 (前端用)"""
    boundary_fw, _ = mixed_firewalls

    resp = client.get('/api/zone-access/firewalls')
    data = resp.json()
    fw_in_resp = next(fw for fw in data['firewalls'] if fw['id'] == boundary_fw.id)

    assert 'is_zone_boundary' in fw_in_resp
    assert fw_in_resp['is_zone_boundary'] == 1
