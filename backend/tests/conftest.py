"""
全局 pytest fixture

- db_session: 内存 SQLite + 每个测试独立事务, 测完回滚
- client: FastAPI TestClient (适配 httpx 0.28+)
- sample_firewall: 工厂函数, 快速造一个测试防火墙
- sample_policy: 同上, 造策略
"""
import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import fastapi_app as app  # 不是 socketio.ASGIApp (那个没 dependency_overrides)
from app.database import Base, get_db
from app.models import Firewall, Policy, Order, OrderStatus, FirewallType, ConnectionType


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
# Factory fixtures - 快速造测试数据
# ============================================================

@pytest.fixture
def sample_firewall(db_session):
    """一个最小可用的防火墙, region='测试区', local='内网', external='DMZ'"""
    from app.models import ZoneAccessConfig
    fw = Firewall(
        name='fw-test',
        alias='测试墙',
        type=FirewallType.fortigate,
        management_ip='10.99.99.1',
        region='测试区',
        local_zone_name='内网',
        external_zone_name='DMZ',
        connection_type=ConnectionType.ssh,
        internal_protected_ips='10.0.0.0/8\n172.16.0.0/12',
        external_protected_ips='192.168.0.0/16',
        is_zone_boundary=1,
        auto_push=0,
    )
    db_session.add(fw)
    db_session.commit()
    db_session.refresh(fw)
    # 同时配 zone_access_configs (FirewallMatcher 用它做 zone_matrix 匹配, 不配则策略匹配不到 firewall)
    # 测试策略用 source_zone='生产区', dest_zone='测试区' (test_preview.py 跨区场景)
    cfg = ZoneAccessConfig(
        source_zone='生产区', dest_zone='测试区', firewall_id=fw.id, description='测试用'
    )
    db_session.add(cfg)
    db_session.commit()
    return fw


@pytest.fixture
def sample_policy(db_session, sample_firewall):
    """一个最小可用的策略, 内网 → DMZ"""
    from app.models import Order
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
        source_zone='内网',
        source_ip='10.1.1.0/24',
        dest_zone='DMZ',
        dest_ip='192.168.1.10',
        service='443',
        action='permit',
        firewall_id=None,
    )
    db_session.add(policy)
    db_session.commit()
    db_session.refresh(policy)
    return policy
