"""推送流水线

完整流程:
1. 加载 Order + Firewall
2. 创建 SSH client
3. 拉设备当前配置 + 解析
4. 创建快照记录（running 状态）
5. 对每条工单策略跑匹配器
6. 生成 CLI 命令
7. 推送到设备
8. 写 PushedPolicyItem 明细
9. 更新快照状态（success/failed/partial）

可通过 progress_callback 实时反馈进度（WebSocket / Celery update）。
"""
from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.policy_matcher import (
    MatchAction,
    MatchResult,
    ObjectReuse,
    PolicyMatcher,
)
from app.core.push_log_writer import PushLogWriter
from app.database import SessionLocal
from app.models import (
    Firewall,
    Order,
    Policy,
    PushedPolicyItem,
    PushedPolicySnapshot,
    PushLog,
    PushLogLevel,
    PushMode,
    PushSnapshotStatus,
)
from app.services.firewall_clients.base import (
    AddressObject,
    FirewallClient,
    FirewallPolicy,
    PushProgress,
    ScheduleObject,
    ServiceObject,
)
from app.services.firewall_clients.registry import create_client, get_client_class


logger = logging.getLogger(__name__)


# ============================================================
# 异常
# ============================================================

class PushPipelineError(Exception):
    pass


# ============================================================
# 流水线
# ============================================================

class PushPipeline:
    """推送流水线（单次推送）"""

    def __init__(
        self,
        order_id: int,
        firewall_id: int,
        mode: str = "deduplicate",
        db: Optional[Session] = None,
    ):
        if mode not in ("deduplicate", "force_push"):
            raise ValueError(f"mode 必须是 'deduplicate' / 'force_push', got {mode!r}")

        self.order_id = order_id
        self.firewall_id = firewall_id
        self.mode = mode

        self._db_provided = db is not None
        self.db = db or SessionLocal()

        # 进度回调: signature = (stage: str, message: str, data: dict)
        self.progress_callback: Optional[Callable] = None

        # 内部状态
        self.snapshot: Optional[PushedPolicySnapshot] = None
        self.client: Optional[FirewallClient] = None
        self.match_results: List[MatchResult] = []
        self.push_results: List[PushProgress] = []
        self._start_time: Optional[float] = None
        # 实时日志: 用 PushLogWriter 独立 session 写 (重构.md §8.1 铁律, 防主事务回滚擦日志)
        # writer 在 snapshot 创建后初始化 (需要 snapshot_id)
        self._log_writer: Optional[PushLogWriter] = None

    # ============================================================
    # 公开 API
    # ============================================================

    def run(self) -> Dict[str, Any]:
        """执行完整流程"""
        self._start_time = time.time()
        try:
            self._emit("start", f"开始推送工单 {self.order_id} 到防火墙 {self.firewall_id}", {
                "order_id": self.order_id, "firewall_id": self.firewall_id, "mode": self.mode,
            })

            # 1) 加载数据
            self._emit("load", "加载工单和防火墙...")
            order = self._load_order()
            firewall = self._load_firewall()

            # 2) 创建客户端 + 测试连接
            self._emit("connect", f"连接防火墙 {firewall.management_ip}...")
            self.client = self._create_client(firewall)
            test_result = self.client.test_connection()
            if not test_result.success:
                raise PushPipelineError(f"连接测试失败: {test_result.error}")

            # 3) 创建快照（先 running 状态）
            self.snapshot = self._create_snapshot(order, firewall)
            # 初始化 PushLogWriter (独立 session, 铁律 §8.1)
            self._log_writer = PushLogWriter.for_snapshot(self.snapshot.id, self.db)
            self._emit("snapshot", f"创建推送快照 #{self.snapshot.id} (batch={self.snapshot.batch_id})")

            # 4) 拉配置 + 解析
            self._emit("fetch", "拉取防火墙当前配置...")
            config_text = self.client.fetch_running_config()
            self._emit("parse", f"解析配置 ({len(config_text)} 字节)...")
            addrs, svcs, scheds, policies = self._parse_with_default(config_text)

            self._emit("fetched", f"拉取到 {len(addrs)} 地址, {len(svcs)} 服务, {len(policies)} 策略", {
                "addresses": len(addrs), "services": len(svcs), "policies": len(policies),
            })

            # 存设备侧快照
            self._save_fetched_snapshot(addrs, svcs, policies)

            # 5) 匹配
            self._emit("match", f"匹配 {len(order.policies)} 条工单策略...")
            matcher = PolicyMatcher(
                mode=self.mode,
                existing_addresses=addrs,
                existing_services=svcs,
                existing_schedules=scheds,
                existing_policies=policies,
            )
            self.match_results = []
            for p in order.policies:
                src_ips = (p.source_ip or "").split()
                dst_ips = (p.dest_ip or "").split()
                ports = (p.service or "").split() if p.service else []
                # 解析有效期
                valid_until = self._extract_valid_until(p)
                result = matcher.match_one(
                    src_ips=src_ips,
                    dst_ips=dst_ips,
                    ports=ports,
                    valid_until=valid_until,
                    rule_name=f"O{order.order_no}-P{p.id}",
                    policy_id=p.id,
                    src_zone=p.source_zone or "any",
                    dst_zone=p.dest_zone or "any",
                )
                self.match_results.append(result)
                self._emit("matched", f"策略 P{p.id} → {result.action.value}", {
                    "policy_id": p.id,
                    "action": result.action.value,
                    "match_key": result.match_key,
                })

            # 统计
            counts = self._count_actions()
            self._emit("count", f"匹配完成: {counts}", counts)

            # 6) 生成命令（把结果转成 client 期望的格式）
            self._emit("generate", "生成 CLI 命令...")
            new_policies = self._build_new_policy_dicts(order, self.match_results)
            all_commands = self.client.generate_commands(
                new_policies=new_policies,
                existing_addresses=addrs,
                existing_services=svcs,
                existing_schedules=scheds,
            )
            self._emit("generated", f"生成 {len(all_commands)} 条命令")

            # 7) 推送
            self._emit("push", f"开始推送 {len(all_commands)} 条命令到 {firewall.management_ip}...")
            self.push_results = self.client.push_commands(
                all_commands,
                progress_callback=self._on_command_pushed,
            )

            # 8) 写明细
            self._emit("persist", "保存推送明细到数据库...")
            self._save_items(self.match_results, all_commands)

            # 9) 更新快照状态
            success_count = sum(1 for r in self.push_results if r.success)
            failed_count = len(self.push_results) - success_count

            if failed_count == 0:
                status = PushSnapshotStatus.success
            elif success_count > 0:
                status = PushSnapshotStatus.partial
            else:
                status = PushSnapshotStatus.failed

            self._finalize_snapshot(status, counts, error_log=None)

            elapsed = int((time.time() - self._start_time) * 1000)
            self._emit("done", f"推送完成（{status.value}），{elapsed}ms", {
                "status": status.value, "elapsed_ms": elapsed,
                "commands": len(all_commands), "failed": failed_count,
            }, level="success" if failed_count == 0 else "warning")

            return {
                "success": True,
                "snapshot_id": self.snapshot.id,
                "batch_id": self.snapshot.batch_id,
                "status": status.value,
                "elapsed_ms": elapsed,
                "counts": counts,
                "commands_total": len(all_commands),
                "commands_failed": failed_count,
            }

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("Push pipeline failed: %s\n%s", e, tb)
            if self.snapshot:
                self._finalize_snapshot(
                    PushSnapshotStatus.failed, {},
                    error_log=f"{e}\n\n{tb}",
                )
            self._emit("error", f"推送失败: {e}", {"error": str(e), "traceback": tb}, level="error")
            return {
                "success": False,
                "snapshot_id": self.snapshot.id if self.snapshot else None,
                "error": str(e),
                "traceback": tb,
            }
        finally:
            if self.client:
                self.client.disconnect()
            if not self._db_provided:
                self.db.close()

    # ============================================================
    # 内部：加载数据
    # ============================================================

    def _load_order(self) -> Order:
        order = self.db.query(Order).filter(Order.id == self.order_id).first()
        if not order:
            raise PushPipelineError(f"工单 {self.order_id} 不存在")
        return order

    def _load_firewall(self) -> Firewall:
        fw = self.db.query(Firewall).filter(Firewall.id == self.firewall_id).first()
        if not fw:
            raise PushPipelineError(f"防火墙 {self.firewall_id} 不存在")
        return fw

    def _create_client(self, fw: Firewall) -> FirewallClient:
        """根据 firewall 的 connection_config 创建 client"""
        cfg = fw.connection_config or {}
        try:
            client = create_client(
                device_type=fw.type.value if hasattr(fw.type, "value") else str(fw.type),
                host=fw.management_ip,
                username=cfg.get("username", ""),
                password=cfg.get("password", ""),
                port=cfg.get("port", 22),
                timeout=cfg.get("timeout", 30),
            )
        except NotImplementedError as e:
            raise PushPipelineError(f"该设备类型暂未实现客户端: {e}")
        return client

    # ============================================================
    # 内部：快照
    # ============================================================

    def _create_snapshot(self, order: Order, firewall: Firewall) -> PushedPolicySnapshot:
        snap = PushedPolicySnapshot(
            order_id=order.id,
            firewall_id=firewall.id,
            batch_id=str(uuid.uuid4()),
            push_mode=PushMode(self.mode),
            status=PushSnapshotStatus.running,
            total_policies=len(order.policies),
            started_at=datetime.utcnow(),
        )
        self.db.add(snap)
        self.db.commit()
        self.db.refresh(snap)
        return snap

    def _save_fetched_snapshot(
        self,
        addrs: List[AddressObject],
        svcs: List[ServiceObject],
        policies: List[FirewallPolicy],
    ):
        if not self.snapshot:
            return
        self.snapshot.fetched_addresses_json = json.dumps(
            [asdict(a) for a in addrs], ensure_ascii=False, default=str
        )
        self.snapshot.fetched_policies_json = json.dumps(
            [asdict(p) for p in policies], ensure_ascii=False, default=str
        )
        # svcs 也可单独存（先放 addresses 里以简化）
        self.db.commit()

    def _finalize_snapshot(
        self,
        status: PushSnapshotStatus,
        counts: Dict[str, int],
        error_log: Optional[str] = None,
    ):
        if not self.snapshot:
            return
        self.snapshot.status = status
        self.snapshot.new_policies = counts.get("created", 0)
        self.snapshot.reused_policies = counts.get("reused", 0)
        self.snapshot.appended_policies = counts.get("appended", 0)
        self.snapshot.failed_policies = counts.get("failed", 0)
        self.snapshot.error_log = error_log
        self.snapshot.finished_at = datetime.utcnow()
        self.db.commit()

    # ============================================================
    # 内部：明细
    # ============================================================

    def _save_items(
        self,
        match_results: List[MatchResult],
        all_commands: List[str],
    ):
        if not self.snapshot:
            return
        # 把 commands 按策略归类（简化: 每条 match 关联若干 command）
        # 实际归类要看 generate_commands 输出顺序；先按平均分
        per_policy_cmds = max(1, len(all_commands) // max(1, len(match_results)))
        for i, r in enumerate(match_results):
            start = i * per_policy_cmds
            end = start + per_policy_cmds if i < len(match_results) - 1 else len(all_commands)
            cmds = all_commands[start:end]
            item = PushedPolicyItem(
                snapshot_id=self.snapshot.id,
                order_id=self.order_id,
                firewall_id=self.firewall_id,
                policy_id=r.policy_id,
                match_key=r.match_key,
                src_addr_key=",".join(r.reuse.src_addrs + r.reuse.new_src_addrs),
                dst_addr_key=",".join(r.reuse.dst_addrs + r.reuse.new_dst_addrs),
                service_key=",".join(r.reuse.services + r.reuse.new_services),
                schedule_key=r.reuse.schedule or (
                    "long-term" if not r.reuse.new_schedule else "new"
                ),
                device_src_obj=",".join(r.reuse.src_addrs) or None,
                device_dst_obj=",".join(r.reuse.dst_addrs) or None,
                device_service_obj=",".join(r.reuse.services) or None,
                device_schedule_obj=r.reuse.schedule,
                device_policy_id=r.existing_device_policy_id,
                device_policy_name=r.existing_device_policy_id,
                action=r.action.value,
                raw_commands="\n".join(cmds),
            )
            self.db.add(item)
        self.db.commit()

    # ============================================================
    # 内部：转换 + 辅助
    # ============================================================

    def _parse_with_default(
        self, config_text: str
    ) -> tuple:
        """调用 client.parse_config 并把空 schedule 转成 []"""
        addrs, svcs, policies = self.client.parse_config(config_text)
        # Schedule 没解析（基类 parse_config 返回 3 个）—— 用空列表
        scheds: List[ScheduleObject] = []
        return addrs, svcs, scheds, policies

    def _build_new_policy_dicts(
        self, order: Order, results: List[MatchResult]
    ) -> List[Dict[str, Any]]:
        """把工单策略 + 匹配结果 组合成 generate_commands 期望的格式"""
        out = []
        for p, r in zip(order.policies, results):
            src_ips = (p.source_ip or "").split() or ["0.0.0.0/0"]
            dst_ips = (p.dest_ip or "").split() or ["0.0.0.0/0"]
            ports = (p.service or "").split() if p.service else []
            out.append({
                "policy_id": p.id,
                "rule_name": f"O{order.order_no}-P{p.id}",
                "src_ips": src_ips,
                "dst_ips": dst_ips,
                "ports": ports,
                "valid_until": self._extract_valid_until(p),
                "src_zone": p.source_zone or "any",
                "dst_zone": p.dest_zone or "any",
                "action": p.action or "permit",
            })
        return out

    @staticmethod
    def _extract_valid_until(p: Policy) -> str:
        """从 Policy 提取有效期字符串"""
        # 优先从 description / raw_data 拿
        if hasattr(p, "valid_until") and p.valid_until:
            return str(p.valid_until)
        # 兼容: 从 description JSON 解析
        if p.description:
            try:
                d = json.loads(p.description)
                if isinstance(d, dict) and d.get("valid_until"):
                    return str(d["valid_until"])
            except Exception:
                pass
        return "长期"

    def _count_actions(self) -> Dict[str, int]:
        c = {"created": 0, "reused": 0, "appended": 0, "failed": 0}
        for r in self.match_results:
            c[r.action.value] = c.get(r.action.value, 0) + 1
        return c

    def _on_command_pushed(self, progress: PushProgress):
        """每条命令推送完的回调"""
        self._emit("command", f"[{progress.seq}] {'✓' if progress.success else '✗'} {progress.command[:80]}", {
            "seq": progress.seq, "success": progress.success, "elapsed_ms": progress.elapsed_ms,
        })

    def _emit(self, stage: str, message: str, data: Optional[dict] = None, level: str = "info"):
        """发进度事件: 写 DB push_logs（前端轮询拿）+ log + 回调

        铁律 (重构.md §8.1): push_logs 写入走 PushLogWriter 独立 session,
        防止主事务回滚擦除推送日志, 故障现场可追溯.

        level: info / success / warning / error
        """
        # 1) callback (外部注入)
        if self.progress_callback:
            try:
                self.progress_callback(stage, message, data or {})
            except Exception:
                pass
        # 2) logger
        logger.info(f"[push {self.snapshot.id if self.snapshot else '?'}] [{stage}] {message}")
        # 3) 写 DB (snapshot 已建之后, 用独立 session 写, 主事务回滚不擦日志)
        if self.snapshot is not None and self._log_writer is not None:
            self._log_writer.write(stage, message, level=level, data=data)
