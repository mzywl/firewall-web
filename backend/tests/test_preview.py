"""
测试预览API
"""
import pytest
from app.models import Policy, Order, Firewall, OrderStatus, FirewallType, ConnectionType


def test_preview_api_returns_expected_structure(client, sample_firewall, db_session):
    """GET /api/workorders/<id>/preview 返回结构正确"""
    # 1) 造工单 (用 db_session fixture, 跟 sample_firewall 同 session, 避免跨 session 可见性问题)
    order = Order(
        order_no='TEST-PREVIEW-001',
        title='preview 测试工单',
        description='pytest',
        status=OrderStatus.pending,
        excel_file_path='/tmp/fake.xlsx',
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    # 2) 造 2 条策略: 1 跨区 (需要 NAT), 1 同区 (不需要)
    # 注: FirewallMatcher.match_by_policy_context 用 policy.source_system_name 跟 zone_access_configs.source_zone 匹配 (业务名维度)
    #     source_zone 字段 011 迁移后是 firewall_matcher 写 internal/external 网络分类, 不放业务名
    p1 = Policy(
        order_id=order.id,
        firewall_id=sample_firewall.id,
        source_system_name='生产区',
        source_ip='10.0.1.100',
        dest_system_name='测试区',
        dest_ip='192.168.1.100',
        service='80',
    )
    p2 = Policy(
        order_id=order.id,
        firewall_id=sample_firewall.id,
        source_system_name='生产区',
        source_ip='10.0.1.101',
        dest_system_name='生产区',
        dest_ip='10.0.2.100',
        service='443',
    )
    db_session.add_all([p1, p2])
    db_session.commit()
    order_id = order.id

    # 3) 调预览 API
    response = client.get(f'/api/workorders/{order_id}/preview')
    assert response.status_code == 200, response.text
    data = response.json()

    # 4) 验证结构
    for key in ('order', 'firewall_groups', 'unmatched_policies', 'warnings', 'errors'):
        assert key in data, f'missing key: {key}'

    # 5) 验证工单信息回填
    assert data['order']['id'] == order_id
    assert data['order']['order_no'] == 'TEST-PREVIEW-001'

    # 6) 验证 firewall_groups 至少 1 个 (sample_firewall 配了 zone_access_configs 生产区→测试区)
    assert len(data['firewall_groups']) >= 1
    group = data['firewall_groups'][0]
    assert group['firewall']['id'] == sample_firewall.id
    # firewall_groups 应有跨区策略 (p1), 同区策略 (p2) 因 sample_firewall.allow_same_firewall_push=0 默认被过滤到 unmatched
    assert len(group['policies']) >= 1
    assert len(data['unmatched_policies']) >= 1  # p2 同墙内部策略

    # 7) 至少 1 条 need_nat=true (跨区策略)
    policies_with_nat = [p for p in group['policies'] if p['nat_info']['need_nat']]
    assert len(policies_with_nat) >= 1


def test_preview_api_404_for_nonexistent_order(client):
    """GET /api/workorders/<不存在的 id>/preview → 404"""
    response = client.get('/api/workorders/9999999/preview')
    assert response.status_code == 404
    assert '工单' in response.json()['detail'] or '不存在' in response.json()['detail']
