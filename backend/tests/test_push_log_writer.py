"""
测试 push_log_writer 独立 session 铁律 (重构.md §8.1)

核心场景:
- 写一条日志能查到
- seq 自增
- 主事务 rollback 不擦日志 (铁律)
- 写失败 best-effort 不抛
- for_snapshot 续号
- message 截断 1000
- level 枚举容错
"""
import pytest
from app.core.push_log_writer import PushLogWriter
from app.models import PushLog, PushLogLevel, PushedPolicySnapshot, PushMode, PushSnapshotStatus
from app.database import SessionLocal, sessionmaker
from app.models import Firewall, Order, OrderStatus, FirewallType, ConnectionType


@pytest.fixture(autouse=True)
def _inject_test_session_factory(db_session, monkeypatch):
    """让 PushLogWriter 走测试 DB (跟 db_session 共享 engine), 不污染 prod DB"""
    TestSession = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    from app.core import push_log_writer as plw
    monkeypatch.setattr(plw, "SessionLocal", TestSession)
    yield


def _make_snapshot(db_session, order_id, firewall_id):
    """造一个最小可用的 PushedPolicySnapshot, 返回 id"""
    import uuid
    s = PushedPolicySnapshot(
        order_id=order_id,
        firewall_id=firewall_id,
        batch_id=str(uuid.uuid4()),
        push_mode=PushMode.force_push,
        status=PushSnapshotStatus.running,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s.id


def _make_order_and_fw(db_session):
    """造一个最小可用的 fw + order (对齐 重构.md §1 spec)

    Firewall 字段: belong_region (was region), 删老 12 字段.
    加 FirewallZone 表达 IP 资产 (老 internal/external_protected_ips 字段已删).
    """
    fw = Firewall(
        name='fw-test', type=FirewallType.fortigate, management_ip='10.99.99.1',
        belong_region='测试区',                          # 新设计: region → belong_region
        connection_type=ConnectionType.ssh, auto_push=0,
    )
    db_session.add(fw); db_session.commit()
    db_session.refresh(fw)
    # 加 FirewallZone 表达 IP 资产
    from app.models import FirewallZone
    db_session.add(FirewallZone(
        firewall_id=fw.id, zone_name='内网',
        protected_ips='10.0.0.0/8', connect_region='测试区',
    ))
    db_session.add(FirewallZone(
        firewall_id=fw.id, zone_name='DMZ',
        protected_ips='192.168.0.0/16', connect_region='生产区',
    ))
    db_session.commit()
    order = Order(
        order_no='TEST-LOG-001', title='log test', status=OrderStatus.pending,
        excel_file_path='/tmp/fake.xlsx',
    )
    db_session.add(order); db_session.commit()
    return order.id, fw.id


def test_push_log_writer_writes_and_queries(db_session):
    """基本功能: 写一条日志, DB 能查到"""
    order_id, fw_id = _make_order_and_fw(db_session)
    sid = _make_snapshot(db_session, order_id, fw_id)

    writer = PushLogWriter(sid)
    ok = writer.write("start", "test log", level="info", data={"k": "v"})
    assert ok is True

    # 用 db_session 查 (跟 PushLogWriter 共享测试 engine)
    logs = db_session.query(PushLog).filter(PushLog.snapshot_id == sid).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.seq == 1
    assert log.stage == "start"
    assert log.message == "test log"
    assert log.level == PushLogLevel.info
    assert '"k"' in log.data_json and '"v"' in log.data_json


def test_push_log_writer_seq_increments(db_session):
    """seq 每次 +1, 从 1 开始"""
    order_id, fw_id = _make_order_and_fw(db_session)
    sid = _make_snapshot(db_session, order_id, fw_id)

    writer = PushLogWriter(sid)
    for i in range(5):
        writer.write("test", f"msg-{i}")

    db_session.expire_all()  # 强制重读 (writer 用了独立 session 写的)
    logs = db_session.query(PushLog).filter(PushLog.snapshot_id == sid).order_by(PushLog.seq).all()
    assert [l.seq for l in logs] == [1, 2, 3, 4, 5]
    assert [l.message for l in logs] == [f"msg-{i}" for i in range(5)]


def test_push_log_writer_survives_main_transaction_rollback(db_session):
    """
    铁律 (重构.md §8.1): 主事务 rollback 也不能擦 PushLog.
    模拟: 写 3 条 PushLog, 然后主事务 raise + rollback, 验证 PushLog 还在.
    """
    order_id, fw_id = _make_order_and_fw(db_session)
    sid = _make_snapshot(db_session, order_id, fw_id)

    # 用 PushLogWriter 写 3 条 (独立 session, 不污染 db_session)
    writer = PushLogWriter(sid)
    writer.write("step1", "before rollback")
    writer.write("step2", "before rollback")
    writer.write("step3", "before rollback")

    # 主事务加一条数据, 然后 raise + rollback (模拟 SSH 失败)
    from app.models import Policy
    db_session.add(Policy(
        order_id=order_id, firewall_id=fw_id,
        source_ip='1.1.1.1', dest_ip='2.2.2.2', service='80',
        device_source_zone='内网', device_dest_zone='DMZ',  # spec §1 强制 NN
    ))
    with pytest.raises(RuntimeError):
        try:
            db_session.flush()
            raise RuntimeError("模拟 SSH 失败")
        except RuntimeError:
            db_session.rollback()
            raise

    # 验证 PushLog 3 条全在 (主事务 rollback 不擦)
    db_session.expire_all()  # 强制重读 (writer 用了独立 session 写的)
    logs = db_session.query(PushLog).filter(PushLog.snapshot_id == sid).order_by(PushLog.seq).all()
    assert len(logs) == 3, f"PushLog 应保留 3 条, 实际 {len(logs)} (主事务 rollback 擦了日志!)"
    assert [l.message for l in logs] == ["before rollback"] * 3


def test_push_log_writer_write_failure_does_not_raise(db_session, monkeypatch):
    """写失败不抛异常 (best-effort, 流水线不能被日志拖垮)"""
    order_id, fw_id = _make_order_and_fw(db_session)
    sid = _make_snapshot(db_session, order_id, fw_id)

    # 模拟 SessionLocal 抛异常
    from app.core import push_log_writer as plw
    def broken_session_local():
        raise RuntimeError("DB 挂了")
    monkeypatch.setattr(plw, "SessionLocal", broken_session_local)

    writer = PushLogWriter(sid)
    # 不应抛异常
    ok = writer.write("test", "should not crash")
    assert ok is False
    assert writer.current_seq == 1  # seq 计数仍更新


def test_push_log_writer_for_snapshot_resumes_seq(db_session):
    """for_snapshot 从 DB max(seq) 续号 (snapshot 重建场景)"""
    order_id, fw_id = _make_order_and_fw(db_session)
    sid = _make_snapshot(db_session, order_id, fw_id)

    # 写 3 条
    w1 = PushLogWriter(sid)
    w1.write("a", "a")
    w1.write("b", "b")
    w1.write("c", "c")
    assert w1.current_seq == 3

    # 重建 writer, 应从 4 开始
    w2 = PushLogWriter.for_snapshot(sid, db_session)
    assert w2.current_seq == 3  # 内部 _seq 还是上次的值
    w2.write("d", "d")
    # 写完 seq=4
    db_session.expire_all()
    logs = db_session.query(PushLog).filter(PushLog.snapshot_id == sid).order_by(PushLog.seq).all()
    assert len(logs) == 4
    assert [l.seq for l in logs] == [1, 2, 3, 4]
    assert [l.message for l in logs] == ["a", "b", "c", "d"]


def test_push_log_writer_for_snapshot_empty_starts_at_zero(db_session):
    """snapshot 还没写日志, for_snapshot 应从 0 开始"""
    order_id, fw_id = _make_order_and_fw(db_session)
    sid = _make_snapshot(db_session, order_id, fw_id)

    writer = PushLogWriter.for_snapshot(sid, db_session)
    assert writer.current_seq == 0
    writer.write("first", "first msg")
    assert writer.current_seq == 1


def test_push_log_writer_truncates_long_message(db_session):
    """message 超过 1000 字符应截断"""
    order_id, fw_id = _make_order_and_fw(db_session)
    sid = _make_snapshot(db_session, order_id, fw_id)

    long_msg = "x" * 5000
    writer = PushLogWriter(sid)
    writer.write("test", long_msg)

    db_session.expire_all()
    log = db_session.query(PushLog).filter(PushLog.snapshot_id == sid).first()
    assert len(log.message) == 1000
    assert log.message == "x" * 1000


def test_push_log_writer_handles_invalid_level(db_session):
    """非法 level 应降级到 info (不抛)"""
    order_id, fw_id = _make_order_and_fw(db_session)
    sid = _make_snapshot(db_session, order_id, fw_id)

    writer = PushLogWriter(sid)
    writer.write("test", "msg", level="invalid_level_xxx")
    writer.write("test", "msg", level="warning")
    writer.write("test", "msg", level="error")

    fresh = SessionLocal()
    try:
        pass
    finally:
        fresh.close()

    db_session.expire_all()
    logs = db_session.query(PushLog).filter(PushLog.snapshot_id == sid).order_by(PushLog.seq).all()
    assert len(logs) == 3
    assert logs[0].level == PushLogLevel.info  # 非法降级
    assert logs[1].level == PushLogLevel.warning
    assert logs[2].level == PushLogLevel.error
