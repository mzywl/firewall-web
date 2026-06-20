"""推送 API

旧端点（保留兼容）:
- POST /api/push/orders/{order_id}/start        启动推送（不带 firewall_id）
- POST /api/push/orders/{order_id}/merge        合并分析
- GET  /api/push/orders/{order_id}/status       推送状态

新端点（v2 推送流水线）:
- POST /api/push/test-connection/{firewall_id}  测试 SSH 连接
- POST /api/push/orders/{order_id}/start-v2     启动 v2 推送（带 firewall_id + mode）
- GET  /api/push/snapshots/{snapshot_id}        查快照详情
- GET  /api/push/snapshots/{snapshot_id}/items  查快照明细
- GET  /api/push/firewall/{firewall_id}/snapshots  查某防火墙历史快照
- GET  /api/push/snapshots                      全部快照（分页）
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.policy_merger import PolicyMerger
from app.core.policy_splitter_v2 import PolicySplitterV2
from app.database import get_db
from app.models import (
    Firewall,
    Order,
    OrderStatus,
    Policy,
    PolicyVersion,
    PushedPolicyItem,
    PushedPolicySnapshot,
    PushLog,
    PushSnapshotStatus,
)
from app.services.firewall_clients.registry import (
    create_client,
    get_client_class,
    supported_types,
)
from app.services.push_pipeline import PushPipeline, PushPipelineError
from app.tasks.push_tasks import push_policies_task

router = APIRouter(prefix="/api/push", tags=["push"])


# ============================================================
# 旧端点（保留兼容）
# ============================================================

@router.post("/orders/{order_id}/start")
def start_push(order_id: int, db: Session = Depends(get_db)):
    """兼容旧版：启动异步推送（无 firewall_id）"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    if order.status == OrderStatus.processing:
        raise HTTPException(status_code=400, detail="工单正在推送中")
    policies_count = db.query(Policy).filter(
        Policy.order_id == order_id,
        Policy.push_status.is_(None)
    ).count()
    if policies_count == 0:
        raise HTTPException(status_code=400, detail="没有待推送的策略")
    task = push_policies_task.delay(order_id)
    return {
        "message": "推送任务已启动",
        "task_id": task.id,
        "order_id": order_id,
        "policies_count": policies_count,
    }


@router.post("/orders/{order_id}/merge")
def merge_policies(order_id: int, db: Session = Depends(get_db)):
    """合并优化策略（保留旧逻辑）"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    policies = db.query(Policy).filter(Policy.order_id == order_id).all()
    if not policies:
        raise HTTPException(status_code=400, detail="没有可合并的策略")
    policies_data = [
        {
            'id': p.id, 'source_ip': p.source_ip, 'dest_ip': p.dest_ip,
            'service': p.service, 'action': p.action,
        }
        for p in policies
    ]
    merger = PolicyMerger()
    merged_data = merger.merge_policies(policies_data)
    redundant_ids = merger.detect_redundant(policies_data)
    return {
        "message": "策略合并分析完成",
        "original_count": len(policies),
        "merged_count": len(merged_data),
        "redundant_count": len(redundant_ids),
        "redundant_ids": redundant_ids,
        "merged_policies": merged_data,
    }


@router.get("/orders/{order_id}/status")
def get_push_status(order_id: int, db: Session = Depends(get_db)):
    """推送状态（旧）"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    total = db.query(Policy).filter(Policy.order_id == order_id).count()
    success = db.query(Policy).filter(
        Policy.order_id == order_id, Policy.push_status == 'success'
    ).count()
    failed = db.query(Policy).filter(
        Policy.order_id == order_id, Policy.push_status == 'failed'
    ).count()
    pending = total - success - failed
    return {
        "order_id": order_id,
        "order_status": order.status,
        "total": total, "success": success, "failed": failed, "pending": pending,
        "progress": int((success + failed) / total * 100) if total > 0 else 0,
    }


# ============================================================
# 新端点：v2 推送
# ============================================================

@router.get("/supported-types")
def get_supported_types():
    """列出已实现的防火墙客户端类型"""
    return {"supported_types": supported_types()}


@router.post("/test-connection/{firewall_id}")
def test_connection(firewall_id: int, db: Session = Depends(get_db)):
    """测试到指定防火墙的 SSH 连接"""
    fw = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    cfg = fw.connection_config or {}
    if not cfg.get("username") or not cfg.get("password"):
        raise HTTPException(
            status_code=400,
            detail="防火墙连接配置缺 username/password（请在编辑防火墙页面配置）",
        )
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
        raise HTTPException(status_code=501, detail=str(e))
    result = client.test_connection()
    return {
        "firewall_id": firewall_id,
        "firewall_name": fw.name,
        "device_type": result.device_type_detected,
        "success": result.success,
        "banner": result.banner[:500],
        "version": result.version[:500],
        "error": result.error,
        "elapsed_ms": result.elapsed_ms,
    }


@router.post("/orders/{order_id}/start-v2")
def start_push_v2(
    order_id: int,
    firewall_id: int = Query(..., description="目标防火墙 ID"),
    mode: str = Query("deduplicate", description="deduplicate / force_push"),
    db: Session = Depends(get_db),
):
    """启动 v2 推送（同步执行；如要异步走 Celery 调用 /tasks/push_v2_task）

    注意：当前是同步执行（方便调试和测试）；真要异步化需要把 run() 拆到 Celery。
    """
    if mode not in ("deduplicate", "force_push"):
        raise HTTPException(
            status_code=400, detail=f"mode 必须是 'deduplicate' / 'force_push', got {mode!r}",
        )
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    fw = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    if not order.policies:
        raise HTTPException(status_code=400, detail="工单没有可推送的策略")

    try:
        pipeline = PushPipeline(order_id=order_id, firewall_id=firewall_id, mode=mode, db=db)
        result = pipeline.run()
    except PushPipelineError as e:
        raise HTTPException(status_code=500, detail=f"推送失败: {e}")

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "未知错误"),
        )
    return result


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    """查快照详情"""
    snap = db.query(PushedPolicySnapshot).filter(
        PushedPolicySnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    return {
        "id": snap.id,
        "order_id": snap.order_id,
        "firewall_id": snap.firewall_id,
        "batch_id": snap.batch_id,
        "push_mode": snap.push_mode.value if hasattr(snap.push_mode, "value") else str(snap.push_mode),
        "status": snap.status.value if hasattr(snap.status, "value") else str(snap.status),
        "total_policies": snap.total_policies,
        "new_policies": snap.new_policies,
        "reused_policies": snap.reused_policies,
        "appended_policies": snap.appended_policies,
        "failed_policies": snap.failed_policies,
        "started_at": snap.started_at.isoformat() if snap.started_at else None,
        "finished_at": snap.finished_at.isoformat() if snap.finished_at else None,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "error_log": snap.error_log,
        "has_fetched_snapshot": bool(
            snap.fetched_addresses_json or snap.fetched_policies_json
        ),
    }


@router.get("/snapshots/{snapshot_id}/logs")
def get_snapshot_logs(
    snapshot_id: int,
    after_seq: int = Query(0, description="只返回 seq > after_seq 的日志（用于前端轮询拿增量）"),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    """查快照的实时日志（按 seq 升序）

    前端轮询模式:
      - 首次: GET /snapshots/{id}/logs 拿前 200 条
      - 后续: GET /snapshots/{id}/logs?after_seq={最后一条 seq} 拿增量
      - 间隔 1.5 秒
    """
    snap = db.query(PushedPolicySnapshot).filter(
        PushedPolicySnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    q = db.query(PushLog).filter(
        PushLog.snapshot_id == snapshot_id,
        PushLog.seq > after_seq,
    ).order_by(PushLog.seq.asc()).limit(limit)
    logs = q.all()
    return {
        "snapshot_id": snapshot_id,
        "snapshot_status": snap.status.value if hasattr(snap.status, "value") else str(snap.status),
        "total": db.query(PushLog).filter(PushLog.snapshot_id == snapshot_id).count(),
        "after_seq": after_seq,
        "logs": [
            {
                "id": lg.id,
                "seq": lg.seq,
                "stage": lg.stage,
                "level": lg.level.value if hasattr(lg.level, "value") else str(lg.level),
                "message": lg.message,
                "data": json.loads(lg.data_json) if lg.data_json else None,
                "created_at": lg.created_at.isoformat() if lg.created_at else None,
            }
            for lg in logs
        ],
    }


@router.get("/snapshots/{snapshot_id}/items")
def get_snapshot_items(
    snapshot_id: int,
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """查快照的策略明细"""
    snap = db.query(PushedPolicySnapshot).filter(
        PushedPolicySnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    items = db.query(PushedPolicyItem).filter(
        PushedPolicyItem.snapshot_id == snapshot_id
    ).order_by(PushedPolicyItem.id).offset(offset).limit(limit).all()
    return {
        "snapshot_id": snapshot_id,
        "total": db.query(PushedPolicyItem).filter(
            PushedPolicyItem.snapshot_id == snapshot_id
        ).count(),
        "items": [
            {
                "id": it.id,
                "policy_id": it.policy_id,
                "match_key": it.match_key,
                "action": it.action,
                "device_policy_id": it.device_policy_id,
                "device_policy_name": it.device_policy_name,
                "device_src_obj": it.device_src_obj,
                "device_dst_obj": it.device_dst_obj,
                "device_service_obj": it.device_service_obj,
                "device_schedule_obj": it.device_schedule_obj,
                "src_addr_key": it.src_addr_key,
                "dst_addr_key": it.dst_addr_key,
                "service_key": it.service_key,
                "schedule_key": it.schedule_key,
                "raw_commands_preview": (it.raw_commands or "")[:500],
                "error_msg": it.error_msg,
                "created_at": it.created_at.isoformat() if it.created_at else None,
            }
            for it in items
        ],
    }


@router.get("/firewall/{firewall_id}/snapshots")
def list_firewall_snapshots(
    firewall_id: int,
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """列某防火墙的历史快照"""
    fw = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    snaps = db.query(PushedPolicySnapshot).filter(
        PushedPolicySnapshot.firewall_id == firewall_id
    ).order_by(PushedPolicySnapshot.id.desc()).offset(offset).limit(limit).all()
    return {
        "firewall_id": firewall_id,
        "firewall_name": fw.name,
        "total": db.query(PushedPolicySnapshot).filter(
            PushedPolicySnapshot.firewall_id == firewall_id
        ).count(),
        "snapshots": [
            {
                "id": s.id,
                "order_id": s.order_id,
                "batch_id": s.batch_id,
                "push_mode": s.push_mode.value if hasattr(s.push_mode, "value") else str(s.push_mode),
                "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                "total": s.total_policies,
                "new": s.new_policies,
                "reused": s.reused_policies,
                "appended": s.appended_policies,
                "failed": s.failed_policies,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
            for s in snaps
        ],
    }


@router.get("/snapshots")
def list_snapshots(
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    order_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """列全部快照（可按工单过滤）"""
    q = db.query(PushedPolicySnapshot)
    if order_id:
        q = q.filter(PushedPolicySnapshot.order_id == order_id)
    snaps = q.order_by(PushedPolicySnapshot.id.desc()).offset(offset).limit(limit).all()
    total = q.count()
    return {
        "total": total,
        "snapshots": [
            {
                "id": s.id,
                "order_id": s.order_id,
                "firewall_id": s.firewall_id,
                "batch_id": s.batch_id,
                "push_mode": s.push_mode.value if hasattr(s.push_mode, "value") else str(s.push_mode),
                "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                "total": s.total_policies,
                "new": s.new_policies,
                "reused": s.reused_policies,
                "appended": s.appended_policies,
                "failed": s.failed_policies,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
            for s in snaps
        ],
    }


# ============================================================
# 本地生成推送脚本（不连设备、不复用现有对象、不写快照）
# ============================================================

@router.post("/orders/{order_id}/generate-script")
def generate_push_script(
    order_id: int,
    firewall_id: int = Query(..., description="目标防火墙 ID"),
    db: Session = Depends(get_db),
):
    """本地生成推送到指定防火墙的 CLI 命令脚本（dry-run / 预览用）

    设计前提:
      - 假设设备上没有可复用的地址/服务/时间对象 → 全部新建
      - 走 PolicySplitterV2 把多 IP 策略拆成单 IP 策略
      - 只保留命中本防火墙 (firewall_id) 的策略
      - 同一 (src_ip, dst_ip, port) 只生成一次对象

    不会做:
      - SSH 连接设备
      - 拉取/解析设备配置
      - 走 PolicyMatcher 复用现有对象
      - 创建 PushedPolicySnapshot / 写 PushedPolicyItem
      - 改任何 DB 状态（只读）

    返回: { success, firewall, order, stats, new_policies, commands, skipped }
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    fw = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    if not order.policies:
        raise HTTPException(status_code=400, detail="工单没有可生成的策略")

    # 1. 校验设备类型有 client 实现
    fw_type = fw.type.value if hasattr(fw.type, "value") else str(fw.type)
    try:
        get_client_class(fw_type)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    # 2. 创建 client（不连接 — host/user/pass 传空也安全，base.__init__ 不主动 connect）
    client = create_client(
        device_type=fw_type,
        host=fw.management_ip or "",
        username="",
        password="",
        port=22,
        timeout=5,
    )

    # 2.5 加载 user_modified 快照, 按 policy.id 索引"使用时间"
    # "使用时间" 不在 Policy 表 (只在 user_modified 快照), 之前硬编码 "长期",
    # 现在透传到 valid_until 字段, generate_commands 自动生成 time-range/schedule 命令
    usage_time_by_id: dict[int, str] = {}
    user_modified_version = db.query(PolicyVersion).filter(
        PolicyVersion.order_id == order_id,
        PolicyVersion.version_type == 'user_modified',
    ).first()
    if user_modified_version:
        for p_dict in user_modified_version.data.get('policies', []):
            pid = p_dict.get('id')
            ut = p_dict.get('使用时间', '')
            if pid is not None:
                usage_time_by_id[pid] = ut

    # 3. 拆分 + 过滤本防火墙命中的策略
    splitter = PolicySplitterV2(db)
    new_policies: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    seen: set = set()  # 防 (src, dst, port) 重复建对象

    for p in order.policies:
        single = splitter.split_policy_to_single_ips(
            p.source_ip or "",
            p.dest_ip or "",
            p.service or "",
            p.action or "permit",
        )
        print (p)
        for idx, sp in enumerate(single):
            if sp["not_pushed_reason"]:
                skipped.append({
                    "policy_id": p.id,
                    "source_ip": sp["source_ip"],
                    "dest_ip": sp["dest_ip"],
                    "reason": sp["not_pushed_reason"],
                })
                continue
            if sp["firewall"] is None or sp["firewall"].id != firewall_id:
                # 不归本防火墙管
                continue

            # 去重: 同一对 (src, dst, port) 只算一条
            ports = (p.service or "").split() if p.service else []
            dedup_key = (sp["source_ip"], sp["dest_ip"], "|".join(ports))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            new_policies.append({
                "policy_id": p.id,
                "rule_name": f"O{order.order_no}-P{p.id}-{idx}",
                "src_ips": [sp["source_ip"]],
                "dst_ips": [sp["dest_ip"]],
                "ports": ports,
                "valid_until": _normalize_valid_until(usage_time_by_id.get(p.id, "长期")),
                "src_zone": p.device_source_zone or "any",
                "dst_zone": p.device_dest_zone or "any",
                "action": p.action or "permit",
            })

    # 4. 生成命令
    try:
        commands = client.generate_commands(
            new_policies=new_policies,
            existing_addresses=[],
            existing_services=[],
            existing_schedules=[],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成命令失败: {e}")

    return {
        "success": True,
        "firewall": {
            "id": fw.id,
            "name": fw.name,
            "type": fw_type,
            "management_ip": fw.management_ip,
        },
        "order": {
            "id": order.id,
            "order_no": order.order_no,
            "title": order.title,
        },
        "stats": {
            "total_order_policies": len(order.policies),
            "to_push": len(new_policies),
            "skipped": len(skipped),
            "commands": len(commands),
        },
        "new_policies": new_policies,
        "commands": commands,
        "skipped": skipped,
    }


def _normalize_valid_until(raw: str) -> str:
    """标准化"使用时间"字段为 generate_commands 能识别的 valid_until 格式

    接受的格式 (来自 user_modified 快照的"使用时间" 字段):
      - 空 / 空白 / "长期" → "长期" (不生成 time-range/schedule)
      - "YYYY-MM-DD" / "YYYY/MM/DD" / "YYYY.MM.DD" → "YYYY-MM-DD" (生成 time-range)
      - 其它不规范 ("6个月", "测试_时间_25", ...) → 兜底 "长期" (不生成, 避免设备拒绝)

    H3C 的 _gen_schedule_object 用 replace("/", "-") 兼容两种,
    Fortigate 的 _build_fortigate_schedule_block 用 replace("-", "/").
    这里统一输出 "YYYY-MM-DD" 中间分隔符, 两家都兼容.
    """
    if not raw:
        return "长期"
    raw = raw.strip()
    if not raw or raw == "长期":
        return "长期"
    # 尝试识别日期: 4位年 + 分隔符 + 1-2位月 + 分隔符 + 1-2位日
    import re
    m = re.match(r'^(\d{4})[\-/.](\d{1,2})[\-/.](\d{1,2})$', raw)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # 兜底: 不规范格式按"长期"处理, 避免推到设备时被拒绝
    return "长期"
