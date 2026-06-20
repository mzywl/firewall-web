"""
回归测试: 使用时间 字段保存 + FIELD_MAP 中→英 字段映射

防 audit 提到的 bug: "SyncScrollTable onUpdate 行为 (这次就是它把中文字段默默吞了)"
后端对应的实现是 orders.py update_policies 里的 FIELD_MAP, 必须固化行为
"""
import pytest


def test_update_policies_accepts_chinese_field_names(client, sample_policy):
    """中文 key 应收进 Policy 表对应英文列"""
    policy_id = sample_policy.id
    r = client.put(
        f'/api/orders/{sample_policy.order_id}/policies',
        json=[{
            'id': policy_id,
            '源IP': '10.1.1.99',         # → source_ip
            '使用时间': '回归测试时间',  # → user_modified 快照
        }],
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['updated_count'] == 1

    # GET /policies 应该用英文 key 拿回 source_ip
    r2 = client.get(f'/api/orders/{sample_policy.order_id}/policies')
    policies = r2.json()
    p = next(p for p in policies if p['id'] == policy_id)
    assert p['源IP'] == '10.1.1.99'
    # 使用时间 应该从 user_modified 快照回填
    assert p['使用时间'] == '回归测试时间'


def test_update_policies_persists_usage_time_to_snapshot(client, sample_policy, db_session):
    """使用时间 不进 Policy 表, 但 user_modified 快照必须有"""
    from app.models import PolicyVersion
    policy_id = sample_policy.id

    r = client.put(
        f'/api/orders/{sample_policy.order_id}/policies',
        json=[{'id': policy_id, '使用时间': '2024-01 至 2024-12'}],
    )
    assert r.status_code == 200, r.text

    # 查 user_modified 快照
    snap = db_session.query(PolicyVersion).filter(
        PolicyVersion.order_id == sample_policy.order_id,
        PolicyVersion.version_type == 'user_modified',
    ).first()
    assert snap is not None
    assert snap.data is not None
    snap_policy = next(p for p in snap.data['policies'] if p['id'] == policy_id)
    assert snap_policy['使用时间'] == '2024-01 至 2024-12'
    # source_ip 应该是 sample_policy 初始值, 不是 None
    assert snap_policy['source_ip'] == sample_policy.source_ip


def test_update_policies_idempotent_when_no_change(client, sample_policy):
    """PUT 同样的值 → updated_count = 0 (避免无意义写)"""
    policy_id = sample_policy.id
    r = client.put(
        f'/api/orders/{sample_policy.order_id}/policies',
        json=[{
            'id': policy_id,
            '源IP': sample_policy.source_ip,  # 跟原值一样
            '使用时间': '',
        }],
    )
    assert r.status_code == 200
    # 没有英文字段实际变化, actual_updated = 0
    assert r.json()['updated_count'] == 0


def test_update_policies_returns_404_for_nonexistent_order(client):
    """不存在的工单 → 404"""
    r = client.put('/api/orders/9999999/policies', json=[{'id': 1, '源IP': 'x'}])
    assert r.status_code == 404
    assert '工单不存在' in r.json()['detail']


def test_update_policies_skips_unknown_policy_id(client, sample_policy):
    """put 里带一个不存在的 policy.id → 跳过 (不报错, 但不更新)"""
    r = client.put(
        f'/api/orders/{sample_policy.order_id}/policies',
        json=[
            {'id': sample_policy.id, '源IP': '10.5.5.5'},  # 有效
            {'id': 999999, '源IP': '10.6.6.6'},            # 无效, 跳过
        ],
    )
    assert r.status_code == 200
    # 只有 sample_policy 实际更新
    assert r.json()['updated_count'] == 1
