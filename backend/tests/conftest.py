"""
全局 pytest fixture

- db_session: 内存 SQLite + 每个测试独立事务, 测完回滚
- client: FastAPI TestClient (适配 httpx 0.28+)
- sample_firewall: 工厂函数, 快速造一个测试防火墙
- sample_policy: 同上, 造策略

新设计 (2026-06-22): 对齐 重构.md §1 spec
  - Firewall 删 covered_region/local_zone_name/external_zone_name/internal_protected_ips/
    external_protected_ips/outbound_snat_pool 等字段
  - zone/NAT 信息改用 FirewallZone + ZoneAccessConfig 表达
  - Firewall.region → Firewall.belong_region
  - ZoneAccessConfig.source_zone → source_region (新增 boundary_source_zone 等 4 字段)
  - Policy 删 action 等字段
"""
import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import fastapi_app as app  # 不是 socketio.ASGIApp (那个没 dependency_overrides)
from app.database import Base, get_db
from app.models import (
    Firewall, Policy, Order, OrderStatus,
    FirewallType, ConnectionType, FirewallZone, ZoneAccessConfig,
)


# 内存 SQLite, 跨 session 共享 (StaticPool)
TEST_DB_URL = 'sqlite:///:memory:'
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={'check_same_thread': False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """覆盖 app.database.get_db, 让 API 走测试 DB"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# 在 app 启动前建表
Base.metadata.create_all(bind=test_engine)
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def db_session():
    """每个测试一个干净 DB"""
    # 重新建表, 隔离测试间数据
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    """FastAPI TestClient (走 fastapi_app, 不是 socketio 包装)"""
    with TestClient(app) as c:
        yield c

@pytest.fixture
def client():
    """FastAPI TestClient (走 fastapi_app, 不是 socketio 包装)"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_db(db_session):
    """TestClient 跟 db_session 共享同一个 session (避免 SQLite memory 跨连接盲区)

    适用: 测试 fixture 自己造数据, 然后调 client 端点验证 (数据能被 client 看到)
    """
    from app.database import get_db as _get_db
    def _override():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[_get_db] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(_get_db, None)


# ============================================================
# Factory fixtures - 快速造测试数据 (对齐 spec)
# ============================================================

@pytest.fixture
def sample_firewall(db_session):
    """一个最小可用的边界防火墙, belong_region='测试区', 内部=Trust, 外部=DMZ

    新设计:
      - 用 FirewallZone 表达 IP 资产 (zone.protected_ips)
      - 用 ZoneAccessConfig 表达 NAT 池 (cfg.snat_pool + boundary_*_zone)
    """
    fw = Firewall(
        name='fw-test',
        alias='测试墙',
        type=FirewallType.fortigate,
        management_ip='10.99.99.1',
        belong_region='测试区',  # 新设计: region → belong_region
        connection_type=ConnectionType.ssh,
        is_zone_boundary=1,
        auto_push=0,
    )
    db_session.add(fw)
    db_session.commit()
    db_session.refresh(fw)

    # 加 FirewallZone (新设计核心: IP 资产 + connect_region)
    zone_internal = FirewallZone(
        firewall_id=fw.id,
        zone_name='内网',
        protected_ips='10.0.0.0/8\n172.16.0.0/12',
        connect_region='测试区',  # zone.connect_region == fw.belong_region → internal
    )
    zone_external = FirewallZone(
        firewall_id=fw.id,
        zone_name='DMZ',
        protected_ips='192.168.0.0/16',
        connect_region='生产区',  # zone.connect_region != fw.belong_region → external
    )
    db_session.add(zone_internal)
    db_session.add(zone_external)
    db_session.commit()

    # 加 ZoneAccessConfig (新设计核心: 边界 + SNAT 池)
    cfg = ZoneAccessConfig(
        firewall_id=fw.id,
        source_region='生产区',
        dest_region='测试区',
        boundary_source_zone='DMZ',
        boundary_dest_zone='内网',
        need_nat=1,
        snat_pool='172.16.99.1',  # SNAT 池让 nat_type=SNAT
        description='测试用',
    )
    db_session.add(cfg)
    db_session.commit()
    return fw


@pytest.fixture
def sample_policy(db_session, sample_firewall):
    """一个最小可用的策略, 内网 → DMZ"""
    order = Order(
        order_no='TEST-001',
        title='测试工单',
        description='pytest',
        status=OrderStatus.pending,
        excel_file_path='/tmp/fake.xlsx',
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    policy = Policy(
        order_id=order.id,
        source_system_name='内网',
        source_ip='10.1.1.0/24',
        dest_system_name='DMZ',
        dest_ip='192.168.1.10',
        service='443',
        firewall_id=sample_firewall.id,  # 新设计: spec 强制 NOT NULL
    )
    db_session.add(policy)
    db_session.commit()
    db_session.refresh(policy)
    return policy


# ============================================================
# 设计文档 §9: 4 防火墙跨大区 + 跨物理墙 seed
#   用途: 端到端压测 chain_planner 的双命中过滤 + 链式改写 + SNAT 透传
# ============================================================
@pytest.fixture
def design_doc_seed(db_session):
    """设计文档 §9 完整测试 seed — 4 台防火墙 + 9 个 zone + 1 个跨大区 cfg

    拓扑:
        生产区                     中央边界墙 fw3         测试区
        fw1 (10.1 + 10.2)         192.168.1.1-1.8 (SNAT)  fw4 (172.16)
        fw2 (10.2 + 10.1)         ←── 需 NAT ──→

    覆盖场景:
        1) 跨大区 (生产→测试): fw1 + fw3 (boundary SNAT) + fw4 (dst 改写)
        2) 同大区跨墙东西向: fw1 + fw2 (无 NAT)
    """
    # --- 防火墙 ---
    fw1 = Firewall(
        name='生产区-物理A墙', type=FirewallType.huawei, management_ip='10.254.1.1',
        belong_region='生产区', connection_type=ConnectionType.ssh,
        is_zone_boundary=0, auto_push=0,
    )
    fw2 = Firewall(
        name='生产区-物理B墙', type=FirewallType.h3c, management_ip='10.254.1.2',
        belong_region='生产区', connection_type=ConnectionType.ssh,
        is_zone_boundary=0, auto_push=0,
    )
    fw3 = Firewall(
        name='中央隔离边界大墙', type=FirewallType.fortigate, management_ip='10.254.99.99',
        belong_region='中央隔离区', connection_type=ConnectionType.ssh,
        is_zone_boundary=1, auto_push=0,
    )
    fw4 = Firewall(
        name='测试区-物理本地墙', type=FirewallType.hillstone, management_ip='10.254.2.1',
        belong_region='测试区', connection_type=ConnectionType.ssh,
        is_zone_boundary=0, auto_push=0,
    )
    db_session.add_all([fw1, fw2, fw3, fw4])
    db_session.commit()
    for fw in [fw1, fw2, fw3, fw4]:
        db_session.refresh(fw)

    # --- FirewallZone (设计文档 §9 §2) ---
    # fw1 (生产A): Trust internal + Untrust external (生产区 + 测试区, 重名 2 行)
    db_session.add_all([
        FirewallZone(firewall_id=fw1.id, zone_name='Trust', zone_role='internal',
                     connect_region='生产区', protected_ips='10.1.0.0/16'),
        FirewallZone(firewall_id=fw1.id, zone_name='Untrust', zone_role='external',
                     connect_region='生产区', protected_ips='10.2.0.0/16'),
        FirewallZone(firewall_id=fw1.id, zone_name='Untrust', zone_role='external',
                     connect_region='测试区', protected_ips='172.16.0.0/16'),
        # fw2 (生产B): Trust + Untrust (同大区, 跨墙东西向)
        FirewallZone(firewall_id=fw2.id, zone_name='Trust', zone_role='internal',
                     connect_region='生产区', protected_ips='10.2.0.0/16'),
        FirewallZone(firewall_id=fw2.id, zone_name='Untrust', zone_role='external',
                     connect_region='生产区', protected_ips='10.1.0.0/16'),
        # fw3 (中央边界): Port_To_Prod + Port_To_Test
        FirewallZone(firewall_id=fw3.id, zone_name='Port_To_Prod', zone_role='external',
                     connect_region='生产区', protected_ips='10.1.0.0/16\n10.2.0.0/16'),
        FirewallZone(firewall_id=fw3.id, zone_name='Port_To_Test', zone_role='external',
                     connect_region='测试区', protected_ips='172.16.0.0/16\n192.168.1.0/24'),
        # fw4 (测试本地): Trust internal + Untrust external (含 SNAT 池段)
        FirewallZone(firewall_id=fw4.id, zone_name='Trust', zone_role='internal',
                     connect_region='测试区', protected_ips='172.16.0.0/16'),
        FirewallZone(firewall_id=fw4.id, zone_name='Untrust', zone_role='external',
                     connect_region='生产区', protected_ips='10.1.0.0/16\n192.168.1.0/24'),
    ])
    db_session.commit()

    # --- ZoneAccessConfig (设计文档 §9 §3) ---
    db_session.add(ZoneAccessConfig(
        firewall_id=fw3.id,
        source_region='生产区', dest_region='测试区',
        boundary_source_zone='Port_To_Prod', boundary_dest_zone='Port_To_Test',
        need_nat=1, snat_pool='192.168.1.1-192.168.1.8',
        description='设计文档 §9: 中央边界墙 NAT 路径',
    ))
    db_session.commit()

    return {
        'fw1': fw1, 'fw2': fw2, 'fw3': fw3, 'fw4': fw4,
        # 帮助测试断言的别名
        'cross_fws': [fw1, fw3, fw4],  # 跨大区触达 3 台
        'east_west_fws': [fw1, fw2],   # 同大区东西向触达 2 台
    }