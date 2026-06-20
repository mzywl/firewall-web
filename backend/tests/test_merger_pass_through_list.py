"""
测试 PolicyMergerV2 合并 src 多 IP 时正确保留 sp 级别的 PASS_THROUGH

回归场景 (坑点 24, 工单 28 ID 163):
  src='10.1.137.137\n192.101.64.2' 合并前:
    - sp1 (10.1.137.137): 直连无 PASS_THROUGH (pass_through=None)
    - sp2 (192.101.64.2): 是 fw6 出向 SNAT 后 IP, 应有 PASS_THROUGH {via fw6, translated 10.223.32.1}
  合并后必须保留 sp2 的 PASS_THROUGH, 不能被 sp1 的 None 覆盖。
"""
from app.core.policy_splitter_v2 import PolicyMergerV2


def _make_fw_mock(fw_id=14, name='fw14'):
    """造一个假 firewall 对象 (merger 只要 .id, 不需要 ORM session)"""
    class FW:
        pass
    fw = FW()
    fw.id = fw_id
    fw.name = name
    return fw


def test_merger_collects_pass_through_from_all_sps():
    """merger 合并 src 多 IP 时, 收集所有 sp 的 pass_through 到 pass_through_list

    修复前 (坑点 24): sp1.pt=None 会覆盖 sp2.pt, sp2 的 PASS_THROUGH 丢光
    修复后: sp1.pt=None 跳过 (不污染 list), sp2.pt 进入 list
    """
    fw = _make_fw_mock()

    pt_fw6 = {
        'translated_src_ip': '10.223.32.1',
        'translated_dst_ip': None,
        'source_zone': 'internal',
        'dest_zone': 'internal',
        'via_firewall': {'id': 6, 'name': '生产测试边界防火墙'},
    }

    policies = [
        # sp1: 直连, 无 PASS_THROUGH
        {
            'source_ip': '10.1.137.137',
            'dest_ip': '10.2.179.130',
            'service': '138-139\n445',
            'firewall': fw,
            'direction': 'inbound',
            'action': 'permit',
            '使用时间': '长期',
            'pass_through': None,  # ← sp1 无 PASS_THROUGH
        },
        # sp2: fw6 SNAT 后 IP, 应该有 PASS_THROUGH
        {
            'source_ip': '192.101.64.2',
            'dest_ip': '10.2.179.130',
            'service': '138-139\n445',
            'firewall': fw,
            'direction': 'inbound',
            'action': 'permit',
            '使用时间': '长期',
            'pass_through': pt_fw6,  # ← sp2 有 PASS_THROUGH
        },
    ]

    merged = PolicyMergerV2.merge_policies(policies)
    assert len(merged) == 1, f'应该合并成 1 条, 实际 {len(merged)}'
    p = merged[0]

    # src 合并正确
    assert p['source_ip'] == '10.1.137.137\n192.101.64.2'

    # 关键断言: pass_through_list 包含 sp2 的 pt, sp1 的 None 没污染 list
    assert p.get('pass_through_list') == [pt_fw6], (
        f'pass_through_list 应该是 [sp2.pt], 实际 {p.get("pass_through_list")}'
    )

    # 顶层 pass_through 字段保留 sp1 的 None (sp1 是第一条)
    # preview.py line 249-251 才把 pass_through_list[0] 修补到顶层
    assert p.get('pass_through') is None


def test_merger_no_pass_through_when_all_sps_none():
    """所有 sp 的 pass_through 都是 None → 不生成 pass_through_list"""
    fw = _make_fw_mock()

    policies = [
        {
            'source_ip': '10.1.1.1',
            'dest_ip': '10.2.2.2',
            'service': '80',
            'firewall': fw,
            'direction': 'inbound',
            'action': 'permit',
            '使用时间': '长期',
            'pass_through': None,
        },
        {
            'source_ip': '10.1.1.2',
            'dest_ip': '10.2.2.2',
            'service': '80',
            'firewall': fw,
            'direction': 'inbound',
            'action': 'permit',
            '使用时间': '长期',
            'pass_through': None,
        },
    ]

    merged = PolicyMergerV2.merge_policies(policies)
    p = merged[0]
    # 全部 None → list 不存在 (没 setdefault 触发)
    assert 'pass_through_list' not in p or not p['pass_through_list']
    assert p.get('pass_through') is None


def test_merger_single_sp_with_pass_through():
    """单 src IP 但有 pt → 也走 list 路径 (list 长度 1, 渲染统一)"""
    fw = _make_fw_mock()

    pt = {
        'translated_src_ip': '10.223.31.1',
        'translated_dst_ip': None,
        'source_zone': 'external',
        'dest_zone': 'internal',
        'via_firewall': {'id': 6, 'name': 'fw6'},
    }

    policies = [{
        'source_ip': '192.101.64.2',
        'dest_ip': '10.2.179.130',
        'service': '80',
        'firewall': fw,
        'direction': 'inbound',
        'action': 'permit',
        '使用时间': '长期',
        'pass_through': pt,
    }]

    merged = PolicyMergerV2.merge_policies(policies)
    p = merged[0]
    assert p.get('pass_through_list') == [pt]
    assert p.get('pass_through') == pt


def test_merger_dedupes_identical_pass_throughs():
    """多条 sp 指向同一个 PASS_THROUGH (例如 src={192.101.64.2, 192.101.64.3} 都经 fw6 同 SNAT 池)

    当前实现不主动 dedup (按 sp 数量展开 PASS_THROUGH 行), 但保持 sp 顺序透传.
    至少验证不崩.
    """
    fw = _make_fw_mock()
    pt = {
        'translated_src_ip': '10.223.32.1',
        'translated_dst_ip': None,
        'source_zone': 'internal',
        'dest_zone': 'internal',
        'via_firewall': {'id': 6, 'name': 'fw6'},
    }
    policies = [
        {'source_ip': '192.101.64.2', 'dest_ip': '10.2.179.130', 'service': '80',
         'firewall': fw, 'direction': 'inbound', 'action': 'permit', '使用时间': '长期',
         'pass_through': pt},
        {'source_ip': '192.101.64.3', 'dest_ip': '10.2.179.130', 'service': '80',
         'firewall': fw, 'direction': 'inbound', 'action': 'permit', '使用时间': '长期',
         'pass_through': {**pt, 'translated_src_ip': '10.223.32.2'}},  # 不同 sp 不同 pool IP
    ]

    merged = PolicyMergerV2.merge_policies(policies)
    p = merged[0]
    assert len(p.get('pass_through_list', [])) == 2


def test_preview_renders_pass_through_list_as_multiple_rows():
    """preview._generate_nat_policies 接受 list[Dict] → 生成多条 PASS_THROUGH 行"""
    from app.api.preview import _generate_nat_policies

    merged_policy = {
        'source_ip': '10.1.137.137\n192.101.64.2',
        'dest_ip': '10.2.179.130',
        'service': '138-139\n445',
        'action': 'permit',
        'direction': 'inbound',
        'source_zone': 'vas-prod-app04',
        'dest_zone': '落地文件共享服务器',
    }
    pt_list = [{
        'translated_src_ip': '10.223.32.1',
        'translated_dst_ip': None,
        'source_zone': 'internal',
        'dest_zone': 'internal',
        'via_firewall': {'id': 6, 'name': 'fw6'},
    }]
    nat_info = {
        'need_nat': False,
        'nat_type': None,
        'source_zone': 'external',
        'dest_zone': 'internal',
        'source_zone_name': 'untrust',
        'dest_zone_name': 'trust',
    }

    rows = _generate_nat_policies(merged_policy, nat_info, pass_through=pt_list)
    assert len(rows) == 1, f'应该渲染 1 条 PASS_THROUGH, 实际 {len(rows)}'
    r = rows[0]
    assert r['type'] == 'PASS_THROUGH'
    assert r['source_ip'] == '10.223.32.1'
    assert r['dest_ip'] == '10.2.179.130'
    assert r['via_firewall']['id'] == 6
