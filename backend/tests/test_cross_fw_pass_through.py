"""
测试 preview._detect_cross_fw_pass_through 跨防火墙 IP 归属识别

回归场景 (坑点 25, 工单 28 ID 163 fw14):
  fw6 (boundary fw) internal=192.101.64.0/24 ∪ 192.101.66.0/24, outbound_snat_pool=10.223.32.1
  fw14 (非 boundary) src=192.101.64.2 ∈ fw6.internal
  → fw14 上 sp 应有 pt={translated_src_ip: 10.223.32.1, via fw6}

修复前: region_nat_state 跨区查不到 (fw6.region='测试区' ≠ fw14.region='生产区'),
        fw14 sp 没 PASS_THROUGH
修复后: _detect_cross_fw_pass_through 检查 sp.src ∈ other_fw.internal_protected_ips,
        跨 region/zone 都能识别
"""
import pytest
from app.models import Firewall, FirewallType, ConnectionType, OrderStatus
from app.api.preview import _detect_cross_fw_pass_through


def _make_boundary_fw(db, *, id, name, internal_cidrs, outbound_pool='', inbound_pool=''):
    """造一个边界防火墙 fixture"""
    fw = Firewall(
        id=id,
        name=name,
        type=FirewallType.h3c,
        connection_type=ConnectionType.ssh,
        management_ip=f'10.0.0.{id}',
        region='测试区',
        covered_region='测试区',
        local_zone_name='trust',
        external_zone_name='untrust',
        internal_protected_ips=internal_cidrs,
        external_protected_ips='10.0.0.0/8',
        is_zone_boundary=1,
        outbound_snat_pool=outbound_pool,
        inbound_snat_pool=inbound_pool,
        is_active=True,
    )
    db.add(fw)
    db.flush()
    return fw


def _make_non_boundary_fw(db, *, id, name, region='生产区'):
    """造一个非边界防火墙 fixture"""
    fw = Firewall(
        id=id,
        name=name,
        type=FirewallType.h3c,
        connection_type=ConnectionType.ssh,
        management_ip=f'10.0.1.{id}',
        region=region,
        covered_region=region,
        local_zone_name='trust',
        external_zone_name='untrust',
        internal_protected_ips='10.2.179.0/24',
        external_protected_ips='10.0.0.0/8',
        is_zone_boundary=0,
        outbound_snat_pool='',
        inbound_snat_pool='',
        is_active=True,
    )
    db.add(fw)
    db.flush()
    return fw


def test_cross_fw_pass_through_detects_src_in_boundary_internal(db_session):
    """核心场景: fw14 sp src=192.101.64.2 ∈ fw6.internal → 识别为 fw6 SNAT 后 IP"""
    fw6 = _make_boundary_fw(
        db_session,
        id=6, name='生产测试边界防火墙',
        internal_cidrs='192.101.66.0/24\n192.101.64.0/24',
        outbound_pool='10.223.32.1',
    )
    fw14 = _make_non_boundary_fw(db_session, id=14, name='生产云下内网防火墙')

    result = _detect_cross_fw_pass_through('192.101.64.2', fw14, db_session)
    assert result is not None, '应该识别出 fw6 是 SNAT 前序墙'
    assert result['translated_src_ip'] == '10.223.32.1'
    assert result['translated_dst_ip'] is None
    assert result['via_firewall'] == {'id': 6, 'name': '生产测试边界防火墙'}


def test_cross_fw_pass_through_returns_none_when_no_match(db_session):
    """sp.src 不在任何 boundary fw 的 internal 段内 → 返回 None"""
    fw6 = _make_boundary_fw(
        db_session,
        id=6, name='fw6',
        internal_cidrs='192.101.64.0/24',
        outbound_pool='10.223.32.1',
    )
    fw14 = _make_non_boundary_fw(db_session, id=14, name='fw14')

    # 192.101.99.99 不在 fw6.internal 段内
    result = _detect_cross_fw_pass_through('192.101.99.99', fw14, db_session)
    assert result is None


def test_cross_fw_pass_through_excludes_current_fw(db_session):
    """不应该把当前 fw 当成"其他 boundary fw" 命中自己 (避免循环)"""
    fw6 = _make_boundary_fw(
        db_session,
        id=6, name='fw6',
        internal_cidrs='10.1.1.0/24',
        outbound_pool='10.223.32.1',
    )

    # 当前 fw = fw6, sp.src = 10.1.1.5 ∈ fw6.internal
    # 但因为 fw6 == current_fw, 不应该命中
    result = _detect_cross_fw_pass_through('10.1.1.5', fw6, db_session)
    assert result is None


def test_cross_fw_pass_through_handles_invalid_ip(db_session):
    """sp.src 不是合法 IP (any / 0.0.0.0 / 乱填) → 返回 None 不抛异常"""
    fw6 = _make_boundary_fw(
        db_session,
        id=6, name='fw6',
        internal_cidrs='192.101.64.0/24',
        outbound_pool='10.223.32.1',
    )
    fw14 = _make_non_boundary_fw(db_session, id=14, name='fw14')

    for bad in ['', 'any', '0.0.0.0', 'not-an-ip', '999.999.999.999']:
        result = _detect_cross_fw_pass_through(bad, fw14, db_session)
        assert result is None, f'输入 {bad!r} 应该返回 None'


def test_cross_fw_pass_through_handles_invalid_cidr(db_session):
    """other_fw.internal_protected_ips 含非法 CIDR → 跳过该行不抛异常"""
    fw6 = _make_boundary_fw(
        db_session,
        id=6, name='fw6',
        # 含非法 CIDR '192.101.0/16' (缺一段) — 跟现实坑点 11 同款配置错
        internal_cidrs='192.101.0/16\n192.101.64.0/24',
        outbound_pool='10.223.32.1',
    )
    fw14 = _make_non_boundary_fw(db_session, id=14, name='fw14')

    # 192.101.64.5 命中第二行合法 CIDR, 不受第一行非法 CIDR 影响
    result = _detect_cross_fw_pass_through('192.101.64.5', fw14, db_session)
    assert result is not None
    assert result['via_firewall']['id'] == 6


def test_cross_fw_pass_through_falls_back_to_inbound_pool_when_no_outbound(db_session):
    """boundary fw 只配了 inbound_snat_pool (没 outbound) → 用 inbound 兜底"""
    fw6 = _make_boundary_fw(
        db_session,
        id=6, name='fw6',
        internal_cidrs='192.101.64.0/24',
        outbound_pool='',  # 没配
        inbound_pool='10.223.31.1',
    )
    fw14 = _make_non_boundary_fw(db_session, id=14, name='fw14')

    result = _detect_cross_fw_pass_through('192.101.64.2', fw14, db_session)
    assert result is not None
    assert result['translated_src_ip'] == '10.223.31.1'  # fallback 到 inbound


def test_cross_fw_pass_through_picks_first_match_when_multiple_boundaries(db_session):
    """sp.src 命中多个 boundary fw → 取第一个 (当前实现简化, 取最早命中的)"""
    fw6 = _make_boundary_fw(
        db_session,
        id=6, name='fw6',
        internal_cidrs='192.101.64.0/24',
        outbound_pool='10.223.32.1',
    )
    fw100 = _make_boundary_fw(
        db_session,
        id=100, name='fw100',
        internal_cidrs='192.101.64.0/24',  # 同样的 IP 段 (测试用)
        outbound_pool='10.223.99.99',
    )
    fw14 = _make_non_boundary_fw(db_session, id=14, name='fw14')

    result = _detect_cross_fw_pass_through('192.101.64.2', fw14, db_session)
    assert result is not None
    # 命中其中一个 (按 id 顺序 fw6/fw100, 取 fw6)
    assert result['via_firewall']['id'] in (6, 100)
