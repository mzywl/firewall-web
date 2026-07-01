"""
PushLog 独立事务写入器 (重构.md §8.1 铁律)

铁律: PushLog 写入必须用独立 session, 防止主事务回滚时擦除推送日志,
导致故障现场不可追溯 (推送到一半 SSH 挂了, rollback 把日志擦了, 运维看不见
"刚才为什么失败").

设计:
- 每个 writer 实例绑定一个 snapshot_id, 维护内部 seq 自增
- 写入时新建独立 SessionLocal, 立即 commit
- 失败 best-effort: 不抛异常, 仅 logger.warning (写日志失败不能影响推送流水线)
- snapshot 重建时调 for_snapshot() 续写, 从 DB max(seq) 续号
"""
import json
import logging
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PushLog, PushLogLevel

logger = logging.getLogger(__name__)


class PushLogWriter:
    """PushLog 独立事务写入器.

    跟 PushPipeline 解耦: 不依赖 self.db / self.snapshot, 自己管 session.
    pipeline 只要在合适时机把 writer 创建好, 后续 _emit() 全走 writer.write().
    """

    def __init__(
        self,
        snapshot_id: int,
        start_seq: int = 0,
        session_factory: Optional[Callable[[], Session]] = None,
    ):
        """
        Args:
            snapshot_id: 绑定 snapshot
            start_seq: 起始 seq (默认 0, 表示下一次 write 写 seq=1)
            session_factory: 独立 session 工厂, 默认 app.database.SessionLocal
                注入用: 测试时换成测试 DB 的 sessionmaker; prod 默认 None
        """
        self.snapshot_id = snapshot_id
        self._seq = start_seq
        self._session_factory = session_factory or SessionLocal

    @classmethod
    def for_snapshot(
        cls,
        snapshot_id: int,
        db: Session,
        session_factory: Optional[Callable[[], Session]] = None,
    ) -> "PushLogWriter":
        """从 DB 读 max(seq), 创建续写 writer (用于 snapshot 重建场景)."""
        max_seq_row = (
            db.query(PushLog.seq)
            .filter(PushLog.snapshot_id == snapshot_id)
            .order_by(PushLog.seq.desc())
            .first()
        )
        start_seq = max_seq_row[0] if max_seq_row else 0
        return cls(snapshot_id, start_seq, session_factory=session_factory)

    def write(
        self,
        stage: str,
        message: str,
        level: str = "info",
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """写一条日志到 push_logs 表, 立即 commit.

        Returns:
            True  - 写入成功
            False - 写入失败 (best-effort, 不抛异常)

        铁律: 此函数不抛异常, 失败只 logger.warning.
        流水线必须能继续, 写日志失败不能成为推送失败的根因.
        """
        self._seq += 1
        try:
            session = self._session_factory()
            try:
                log = PushLog(
                    snapshot_id=self.snapshot_id,
                    seq=self._seq,
                    stage=stage,
                    level=(
                        PushLogLevel(level)
                        if level in {l.value for l in PushLogLevel}
                        else PushLogLevel.info
                    ),
                    message=message[:1000],
                    data_json=(
                        json.dumps(data, ensure_ascii=False, default=str) if data else None
                    ),
                )
                session.add(log)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            logger.warning(
                f"PushLogWriter.write 失败 (snapshot={self.snapshot_id}, seq={self._seq}): {e}"
            )
            return False

    @property
    def current_seq(self) -> int:
        """当前 seq (最后一次写入的 seq, 0 表示还没写过)."""
        return self._seq
