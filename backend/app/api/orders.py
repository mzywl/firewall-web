from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import uuid
import logging
from datetime import datetime

from app.database import get_db
from app.models import Order, Policy, OrderStatus, PolicyVersion
from app.schemas import OrderResponse, OrderCreate, PolicyResponse
from app.core.excel_parser import ExcelParser
from app.core.firewall_matcher import FirewallMatcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])

# 文件上传目录
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload", response_model=OrderResponse)
async def upload_excel(
        file: UploadFile = File(...),
        title: str = None,
        created_by: str = None,
        db: Session = Depends(get_db)
):
    """
    上传 Excel 文件并创建工单
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="只支持 Excel 文件（.xlsx, .xls）")

    try:
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        parser = ExcelParser(file_path)
        excel_data = parser.parse()

        order_no = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        order = Order(
            order_no=order_no,
            title=title or file.filename,
            description=f"上传文件: {file.filename}, 共 {excel_data['total_rows']} 行数据",
            excel_file_path=file_path,
            status=OrderStatus.pending,
            created_by=created_by
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        # 备份历史版本快照
        for v_type in ['original', 'formatted_v1', 'formatted_v2']:
            version_record = PolicyVersion(
                order_id=order.id,
                version_type=v_type,
                data={'policies': excel_data.get(f'{v_type}_data', [])}
            )
            db.add(version_record)
        db.commit()
        return {
            "id": order.id, "order_no": order.order_no, "title": order.title,
            "description": order.description, "status": order.status,
            "excel_file_path": order.excel_file_path, "created_by": order.created_by,
            "created_at": order.created_at, "updated_at": order.updated_at,
            "original_data": excel_data['original_data'],
            "formatted_v1_data": excel_data['formatted_v1_data'],
            "formatted_v2_data": excel_data['formatted_v2_data']
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"文件处理失败: {str(e)}")


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    """
    【此前漏掉的路由 1】：获取工单详情
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    return order


@router.get("/{order_id}/policies")
def get_order_policies(order_id: int, version: str = None, db: Session = Depends(get_db)):
    """
    获取工单的所有策略
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    if version:
        policy_version = db.query(PolicyVersion).filter(
            PolicyVersion.order_id == order_id, PolicyVersion.version_type == version
        ).first()

        if not policy_version and version == 'user_modified':
            return db.query(Policy).filter(Policy.order_id == order_id).all()
        if not policy_version:
            raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")

        return [{
            'id': idx + 1, 'order_id': order_id,
            'created_at': policy_version.created_at.isoformat() if policy_version.created_at else datetime.now().isoformat(),
            **policy_dict
        } for idx, policy_dict in enumerate(policy_version.data.get('policies', []))]

    policies = db.query(Policy).filter(Policy.order_id == order_id).all()
    result = []
    for policy in policies:
        result.append({
            'id': policy.id,
            'order_id': policy.order_id,
            'created_at': policy.created_at.isoformat() if policy.created_at else None,
            '源端系统-环境-用途': policy.source_system_name or '',
            '源IP': policy.source_ip or '',
            '源安全域': policy.device_source_zone or '',
            '目的端系统-环境-用途': policy.dest_system_name or '',
            '目的IP': policy.dest_ip or '',
            '目的安全域': policy.device_dest_zone or '',
            '目的端口': policy.service or '',
            '使用时间': policy.usage_time or '',
        })
    return result


@router.delete("/{order_id}/policies/{policy_id}", status_code=204)
def delete_order_policy(
    order_id: int, policy_id: int, db: Session = Depends(get_db)
):
    """
    删除工单下的某条策略 (2026-06-22: 给策略预览页 "删除" 按钮用)

    铁律:
      - 只能删原始 Excel 导入的策略 (Policy 表), 推上墙后的 (PushedPolicyItem) 不归本接口
      - 删之前先查 order 存在 (防 404 漏检)
      - 删 Policy 同时清掉 user_modified 快照里的对应条目, 避免下次 preview 又显出来
    """
    from app.models import Policy, PolicyVersion

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    policy = db.query(Policy).filter(
        Policy.id == policy_id, Policy.order_id == order_id
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail=f"策略 {policy_id} 不存在")

    db.delete(policy)
    db.flush()

    from sqlalchemy.orm.attributes import flag_modified
    user_modified = db.query(PolicyVersion).filter(
        PolicyVersion.order_id == order_id,
        PolicyVersion.version_type == "user_modified",
    ).first()
    if user_modified and user_modified.data:
        policies_in_snap = user_modified.data.get("policies", [])
        before = len(policies_in_snap)
        user_modified.data["policies"] = [
            p for p in policies_in_snap if p.get("id") != policy_id
        ]
        if len(user_modified.data["policies"]) != before:
            flag_modified(user_modified, "data")
            db.flush()

    db.commit()
    return None


@router.get("/{order_id}/versions")
def get_order_versions(order_id: int, db: Session = Depends(get_db)):
    """
    【此前漏掉的路由 2】：获取工单的所有版本列表
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    versions = db.query(PolicyVersion).filter(
        PolicyVersion.order_id == order_id
    ).order_by(PolicyVersion.created_at).all()

    return [
        {
            "id": v.id,
            "version_type": v.version_type,
            "created_at": v.created_at,
            "policy_count": len(v.data.get('policies', []))
        }
        for v in versions
    ]


@router.put("/{order_id}/policies")
def update_policies(order_id: int, policies_data: List[dict], db: Session = Depends(get_db)):
    """
    前端传来的策略数据直接覆盖：
    1. 覆盖 Policy 表
    2. 覆盖 user_modified 版本
    不做任何合并、不做匹配、不做自动逻辑
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    try:
        updated_count = 0

        # 1. 直接落库到 Policy 表
        for incoming in policies_data:
            p_id = incoming.get("id")
            if not p_id:
                continue

            policy_obj = db.query(Policy).filter(
                Policy.id == p_id,
                Policy.order_id == order_id
            ).first()

            if not policy_obj:
                continue

            # 直接覆盖字段（前端传什么就写什么）
            policy_obj.source_system_name = incoming.get("源端系统-环境-用途")
            policy_obj.source_ip = incoming.get("源IP")
            policy_obj.device_source_zone = incoming.get("源安全域")
            policy_obj.dest_system_name = incoming.get("目的端系统-环境-用途")
            policy_obj.dest_ip = incoming.get("目的IP")
            policy_obj.device_dest_zone = incoming.get("目的安全域")
            policy_obj.service = incoming.get("目的端口")
            policy_obj.usage_time = incoming.get("使用时间")
            policy_obj.firewall_id = incoming.get("firewall_id")

            updated_count += 1

        # 2. 覆盖 user_modified 快照
        from sqlalchemy.orm.attributes import flag_modified

        user_version = db.query(PolicyVersion).filter(
            PolicyVersion.order_id == order_id,
            PolicyVersion.version_type == "user_modified"
        ).first()

        if user_version:
            user_version.data = {"policies": policies_data}
            flag_modified(user_version, "data")
        else:
            user_version = PolicyVersion(
                order_id=order_id,
                version_type="user_modified",
                data={"policies": policies_data}
            )
            db.add(user_version)

        # 清除旧 execution_plan
        db.query(PolicyVersion).filter(
            PolicyVersion.order_id == order_id,
            PolicyVersion.version_type == "execution_plan"
        ).delete()

        db.commit()

        return {
            "message": "策略已直接覆盖更新（Policy + user_modified）",
            "updated_count": updated_count
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
