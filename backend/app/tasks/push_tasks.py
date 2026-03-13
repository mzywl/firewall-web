"""
推送任务模块
"""
from celery import Task
from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models import Order, Policy, Firewall, OperationLog, OrderStatus
from app.core.websocket import broadcast_push_progress, broadcast_push_log, broadcast_push_status
import asyncio
import time


class PushTask(Task):
    """推送任务基类"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        print(f"Task {task_id} failed: {exc}")


@celery_app.task(base=PushTask, bind=True)
def push_policies_task(self, order_id: int):
    """
    推送策略到防火墙（异步任务）
    """
    db = SessionLocal()
    
    try:
        # 获取工单
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise Exception(f"工单 {order_id} 不存在")
        
        # 更新工单状态
        order.status = OrderStatus.processing
        db.commit()
        
        # 广播状态变更
        asyncio.run(broadcast_push_status(order_id, {
            'status': 'processing',
            'message': '开始推送策略'
        }))
        
        # 获取所有待推送的策略
        policies = db.query(Policy).filter(
            Policy.order_id == order_id,
            Policy.push_status.is_(None)
        ).all()
        
        total = len(policies)
        success_count = 0
        failed_count = 0
        
        # 逐个推送策略
        for idx, policy in enumerate(policies, 1):
            try:
                # 获取防火墙配置
                firewall = db.query(Firewall).filter(
                    Firewall.id == policy.firewall_id
                ).first()
                
                if not firewall:
                    raise Exception(f"防火墙 {policy.firewall_id} 不存在")
                
                # 广播推送日志
                asyncio.run(broadcast_push_log(order_id, {
                    'level': 'info',
                    'message': f"正在推送策略 {idx}/{total}: {policy.source_ip} -> {policy.dest_ip}",
                    'timestamp': time.time()
                }))
                
                # 模拟推送（实际应该调用 SSH 推送）
                result = self._push_to_firewall(firewall, policy)
                
                # 更新策略状态
                policy.push_status = 'success' if result['success'] else 'failed'
                policy.push_result = result['message']
                policy.pushed_at = db.func.now()
                
                if result['success']:
                    success_count += 1
                else:
                    failed_count += 1
                
                # 广播进度
                progress = int((idx / total) * 100)
                asyncio.run(broadcast_push_progress(order_id, {
                    'progress': progress,
                    'current': idx,
                    'total': total,
                    'success': success_count,
                    'failed': failed_count
                }))
                
                db.commit()
                
                # 模拟延迟
                time.sleep(0.5)
                
            except Exception as e:
                failed_count += 1
                policy.push_status = 'failed'
                policy.push_result = str(e)
                db.commit()
                
                asyncio.run(broadcast_push_log(order_id, {
                    'level': 'error',
                    'message': f"推送失败: {str(e)}",
                    'timestamp': time.time()
                }))
        
        # 更新工单状态
        if failed_count == 0:
            order.status = OrderStatus.completed
            final_status = 'completed'
            final_message = f'推送完成，成功 {success_count} 条'
        else:
            order.status = OrderStatus.failed
            final_status = 'failed'
            final_message = f'推送完成，成功 {success_count} 条，失败 {failed_count} 条'
        
        db.commit()
        
        # 广播最终状态
        asyncio.run(broadcast_push_status(order_id, {
            'status': final_status,
            'message': final_message,
            'success_count': success_count,
            'failed_count': failed_count
        }))
        
        # 记录操作日志
        log = OperationLog(
            order_id=order_id,
            operation_type='push',
            operation_detail=final_message,
            result='success' if failed_count == 0 else 'failed'
        )
        db.add(log)
        db.commit()
        
        return {
            'success': failed_count == 0,
            'total': total,
            'success_count': success_count,
            'failed_count': failed_count
        }
        
    except Exception as e:
        db.rollback()
        
        # 更新工单状态为失败
        order = db.query(Order).filter(Order.id == order_id).first()
        if order:
            order.status = OrderStatus.failed
            db.commit()
        
        # 广播错误
        asyncio.run(broadcast_push_status(order_id, {
            'status': 'failed',
            'message': f'推送失败: {str(e)}'
        }))
        
        raise
        
    finally:
        db.close()
    
    def _push_to_firewall(self, firewall: Firewall, policy: Policy) -> dict:
        """
        推送策略到防火墙
        TODO: 实现实际的 SSH 推送逻辑
        """
        # 模拟推送
        import random
        success = random.random() > 0.1  # 90% 成功率
        
        if success:
            return {
                'success': True,
                'message': f'成功推送到 {firewall.name}'
            }
        else:
            return {
                'success': False,
                'message': f'推送到 {firewall.name} 失败: 连接超时'
            }
