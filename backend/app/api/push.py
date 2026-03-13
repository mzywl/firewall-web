from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Order, Policy, OrderStatus
from app.tasks.push_tasks import push_policies_task
from app.core.policy_merger import PolicyMerger

router = APIRouter(prefix="/api/push", tags=["push"])


@router.post("/orders/{order_id}/start")
def start_push(order_id: int, db: Session = Depends(get_db)):
    """
    开始推送策略
    """
    # 检查工单是否存在
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    # 检查工单状态
    if order.status == OrderStatus.processing:
        raise HTTPException(status_code=400, detail="工单正在推送中")
    
    # 检查是否有待推送的策略
    policies_count = db.query(Policy).filter(
        Policy.order_id == order_id,
        Policy.push_status.is_(None)
    ).count()
    
    if policies_count == 0:
        raise HTTPException(status_code=400, detail="没有待推送的策略")
    
    # 启动异步推送任务
    task = push_policies_task.delay(order_id)
    
    return {
        "message": "推送任务已启动",
        "task_id": task.id,
        "order_id": order_id,
        "policies_count": policies_count
    }


@router.post("/orders/{order_id}/merge")
def merge_policies(order_id: int, db: Session = Depends(get_db)):
    """
    合并优化策略
    """
    # 检查工单是否存在
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    # 获取所有策略
    policies = db.query(Policy).filter(Policy.order_id == order_id).all()
    
    if not policies:
        raise HTTPException(status_code=400, detail="没有可合并的策略")
    
    # 转换为字典格式
    policies_data = [
        {
            'id': p.id,
            'source_ip': p.source_ip,
            'dest_ip': p.dest_ip,
            'service': p.service,
            'action': p.action
        }
        for p in policies
    ]
    
    # 执行合并
    merger = PolicyMerger()
    merged_data = merger.merge_policies(policies_data)
    
    # 检测冗余策略
    redundant_ids = merger.detect_redundant(policies_data)
    
    return {
        "message": "策略合并分析完成",
        "original_count": len(policies),
        "merged_count": len(merged_data),
        "redundant_count": len(redundant_ids),
        "redundant_ids": redundant_ids,
        "merged_policies": merged_data
    }


@router.get("/orders/{order_id}/status")
def get_push_status(order_id: int, db: Session = Depends(get_db)):
    """
    获取推送状态
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    # 统计策略推送状态
    total = db.query(Policy).filter(Policy.order_id == order_id).count()
    success = db.query(Policy).filter(
        Policy.order_id == order_id,
        Policy.push_status == 'success'
    ).count()
    failed = db.query(Policy).filter(
        Policy.order_id == order_id,
        Policy.push_status == 'failed'
    ).count()
    pending = total - success - failed
    
    return {
        "order_id": order_id,
        "order_status": order.status,
        "total": total,
        "success": success,
        "failed": failed,
        "pending": pending,
        "progress": int((success + failed) / total * 100) if total > 0 else 0
    }
