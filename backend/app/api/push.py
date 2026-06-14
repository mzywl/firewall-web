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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.policy_merger import PolicyMerger
from app.database import get_db
from app.models import (
    Firewall,
    Order,
    OrderStatus,
    Policy,
    PushedPolicyItem,
    PushedPolicySnapshot,
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
