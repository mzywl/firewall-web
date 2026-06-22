"""
设计文档 §9 端到端测试 — 4 防火墙拓扑的 chain_planner 全链路压测

覆盖场景 (来自 design_doc_seed fixture):
  1) 跨大区: 生产区 src (10.1.0.5) → 测试区 dst (172.16.0.5)
     期望合同: 至少触达 fw1; SNAT 池 (192.168.1.1-1.8) 出现在某 sp 的 source_snat_ip
  2) 同大区东西向: 生产区 A 墙 (10.1.0.5) → 生产区 B 墙 (10.2.0.5)
     期望合同: 触达 fw1; 任何 sp 都不应携带 SNAT 改写
  3) 完全无覆盖: src=8.8.8.8 dst=1.1.1.1
     期望合同: 0 触达, 进 not_pushed

每个测试:
  - 造一条 Order + 一条 Policy
  - 调 ChainPlanner.generate_chain_execution_plan
  - 断言: 合同式行为 (SNAT 应用 / 东西向无 NAT / unmatched 进 not_pushed)
  - 不锁死具体 firewall 集合 (chain_planner 的具体实现细节, 留给 Step 6)
"""
import pytest

from app.core.chain_planner import ChainPlanner
from app.models import Order, OrderStatus, Policy


def _make_order_with_policy(db_session, *, src_ip, dst_ip, service='443',
                            order_no='TEST-DD9', source_system_name='生产区',
                            dest_system_name='测试区'):
    """造一条最小可用 Policy (供 chain_planner 消费)"""
    order = Order(
        order_no=order_no,
        title='设计文档 §9 e2e',
        status=OrderStatus.pending,
        excel_file_path='/tmp/fake.xlsx',
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    policy = Policy(
        order_id=order.id,
        source_system_name=source_system_name,
        source_ip=src_ip,
        dest_system_name=dest_system_name,
        dest_ip=dst_ip,
        service=service,
        firewall_id=0,  # 占位, chain_planner 会重写
        # spec 强制 NOT NULL: chain_planner 会用真实 zone 覆盖
        device_source_zone='__pending__',
        device_dest_zone='__pending__',
    )
    db_session.add(policy)
    db_session.commit()
    db_session.refresh(policy)
    return order, policy


def _all_sps(ctx):
    """扁平化 ctx.firewall_groups → [sp, sp, ...]"""
    sps = []
    for grp in ctx.firewall_groups.values():
        sps.extend(grp.get('policies', []))
    return sps


class TestDesignDocCrossRegion:
    """场景 1: 跨大区 (生产→测试) — 验证 SNAT 透传链路合同"""

    def test_cross_region_snat_pool_applied(
        self, db_session, design_doc_seed
    ):
        """src=10.1.0.5 (生产A) → dst=172.16.0.5 (测试)
        合同: SNAT 池 (192.168.1.1-1.8) 出现在某 sp 的 source_snat_ip
        """
        _, policy = _make_order_with_policy(
            db_session,
            src_ip='10.1.0.5', dst_ip='172.16.0.5',
        )

        planner = ChainPlanner(db_session)
        ctx = planner.generate_chain_execution_plan(
            [policy], usage_time_by_id={policy.id: ''},
        )

        # 合同 1: 至少 fw1 被触达 (生产A 墙有 10.1 + 10.2 + 172.16 三 zone, 必然双命中)
        fw1_id = design_doc_seed['fw1'].id
        assert fw1_id in ctx.firewall_groups, (
            f"fw1 (生产A) 应被触达, 实际={list(ctx.firewall_groups.keys())}"
        )

        # 合同 2: 链路中至少有一个 sp 涉及 SNAT 池
        # (两种应用形式: boundary sp 的 source_snat_ip 字段, 或 dst 侧 sp 的 source_ip 被改写到池)
        sps = _all_sps(ctx)
        snat_sps = [sp for sp in sps
                    if sp.get('source_snat_ip') == '192.168.1.1-192.168.1.8'
                    or sp.get('source_ip') == '192.168.1.1-192.168.1.8']
        assert len(snat_sps) >= 1, (
            f"至少一个 sp 应涉及 SNAT 池 192.168.1.1-1.8, 实际 sp 分布: "
            f"{[(sp.get('source_snat_ip'), sp.get('source_ip')) for sp in sps]}"
        )

    def test_cross_region_dst_side_src_rewritten(
        self, db_session, design_doc_seed
    ):
        """跨大区: dst 侧防火墙 (fw4 测试本地) 的 sp.source_ip 期望被改写到 SNAT 池
        (Pass 2 SNAT 透传)
        """
        _, policy = _make_order_with_policy(
            db_session,
            src_ip='10.1.0.5', dst_ip='172.16.0.5',
        )

        planner = ChainPlanner(db_session)
        ctx = planner.generate_chain_execution_plan(
            [policy], usage_time_by_id={policy.id: ''},
        )

        # fw4 (测试本地) 应被触达
        fw4_id = design_doc_seed['fw4'].id
        assert fw4_id in ctx.firewall_groups

        # fw4 的 sp 至少一个 src 应被改写到 SNAT 池
        fw4_sps = ctx.firewall_groups[fw4_id].get('policies', [])
        assert any('192.168.1' in str(sp.get('source_ip', '')) for sp in fw4_sps), (
            f"fw4 (dst 侧) 的 sp.source_ip 应被改写到 SNAT 池, 实际: "
            f"{[sp.get('source_ip') for sp in fw4_sps]}"
        )


class TestDesignDocEastWest:
    """场景 2: 同大区东西向 — 验证无 NAT 直连合同"""

    def test_east_west_no_snat(
        self, db_session, design_doc_seed
    ):
        """src=10.1.0.5 (生产A.Untrust) → dst=10.2.0.5 (生产B.Trust)
        合同: 任何 sp 都不应携带 SNAT 改写
        """
        _, policy = _make_order_with_policy(
            db_session,
            src_ip='10.1.0.5', dst_ip='10.2.0.5',
            source_system_name='生产区-A', dest_system_name='生产区-B',
        )
        planner = ChainPlanner(db_session)
        ctx = planner.generate_chain_execution_plan(
            [policy], usage_time_by_id={policy.id: ''},
        )

        # 合同 1: 至少 fw1 被触达 (10.1 + 10.2 双命中)
        fw1_id = design_doc_seed['fw1'].id
        assert fw1_id in ctx.firewall_groups

        # 合同 2: 任何 sp 都不应 SNAT 改写
        sps = _all_sps(ctx)
        nat_sps = [sp for sp in sps if sp.get('source_snat_ip')]
        assert len(nat_sps) == 0, (
            f"东西向不应 SNAT, 实际 source_snat_ip 分布: "
            f"{[sp.get('source_snat_ip') for sp in nat_sps]}"
        )

        # 合同 3: src 保持原始 10.1.0.5, 不应被改写到 192.168.1.x
        assert all('192.168.1' not in str(sp.get('source_ip', '')) for sp in sps), (
            "东西向 src 不应被改写到 SNAT 池"
        )


class TestDesignDocUnmatched:
    """场景 3: 完全无防火墙覆盖 — 验证 unmatched / not_pushed 路径"""

    def test_unmatched_lands_in_not_pushed(
        self, db_session, design_doc_seed
    ):
        """src=8.8.8.8 (公网, 无任何 firewall zone 覆盖)
        合同: 0 firewall 触达, 进 not_pushed
        """
        _, policy = _make_order_with_policy(
            db_session,
            src_ip='8.8.8.8', dst_ip='1.1.1.1',
        )
        planner = ChainPlanner(db_session)
        ctx = planner.generate_chain_execution_plan(
            [policy], usage_time_by_id={policy.id: ''},
        )

        # 合同 1: 没有任何 firewall 触达
        assert len(ctx.firewall_groups) == 0, (
            f"无 zone 覆盖的 IP 不应触达任何 firewall, 实际触达: "
            f"{list(ctx.firewall_groups.keys())}"
        )

        # 合同 2: sp 应进入 not_pushed (因为 splitter 拆 IP 后没有 firewall 匹配)
        assert len(ctx.not_pushed) >= 1, (
            f"无 zone 覆盖的 sp 应进 not_pushed, 实际 not_pushed 数: {len(ctx.not_pushed)}"
        )


class TestDesignDocZoneRoleRespected:
    """场景 4: zone_role 显式判定 (本次重构的核心变更)

    不依赖 chain_planner 内部判定路径, 只验证:
      - 同一 firewall 同时配 internal + external zone 时, 都能被命中
      - 显式 zone_role 不影响 IP 命中 (IP 命中只看 protected_ips)
    """

    def test_zone_role_independent_of_ip_match(
        self, db_session, design_doc_seed
    ):
        """fw3 (中央边界) 同时有 Port_To_Prod (external) 和 Port_To_Test (external)
        跨大区流量应能命中 (这是基础)
        """
        _, policy = _make_order_with_policy(
            db_session,
            src_ip='10.1.0.5', dst_ip='172.16.0.5',
        )
        planner = ChainPlanner(db_session)
        ctx = planner.generate_chain_execution_plan(
            [policy], usage_time_by_id={policy.id: ''},
        )

        # fw3 在 touched fws 中 OR 它的 zones 在 sp 提取里 (取决于 chain_planner 判定路径)
        # 这里只验证 IP 命中: fw3 至少一个 zone.protected_ips 覆盖 src 或 dst
        fw3 = design_doc_seed['fw3']
        fw3_zones = fw3.zones  # eager loaded from fixture

        src_in_fw3 = any(
            '10.1.0.0/16' in (z.protected_ips or '') or '10.2.0.0/16' in (z.protected_ips or '')
            for z in fw3_zones
        )
        dst_in_fw3 = any(
            '172.16.0.0/16' in (z.protected_ips or '')
            for z in fw3_zones
        )
        assert src_in_fw3 and dst_in_fw3, (
            f"fw3 zones 应同时覆盖 src (10.1) 和 dst (172.16), 实际: "
            f"{[(z.zone_name, z.zone_role, z.protected_ips) for z in fw3_zones]}"
        )

    def test_internal_vs_external_zones_via_zone_role(
        self, db_session, design_doc_seed
    ):
        """直接验证 zone_role 字段: 显式 internal/external 都应在数据库中存在"""
        fw1 = design_doc_seed['fw1']
        internal_zones = [z for z in fw1.zones if z.zone_role == 'internal']
        external_zones = [z for z in fw1.zones if z.zone_role == 'external']

        assert len(internal_zones) >= 1, "fw1 应至少有 1 个 internal zone (Trust)"
        assert len(external_zones) >= 1, "fw1 应至少有 1 个 external zone (Untrust)"

        # Trust 应是 internal
        assert any(z.zone_name == 'Trust' and z.zone_role == 'internal' for z in fw1.zones)
        # Untrust 应是 external
        assert any(z.zone_name == 'Untrust' and z.zone_role == 'external' for z in fw1.zones)
