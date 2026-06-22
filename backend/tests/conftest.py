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