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

        # 解析数据并调用严格匹配器写入 Policy 表
        matcher = FirewallMatcher(db)
        for row in excel_data['data']:
            policy = Policy(
                order_id=order.id,
                source_system_name=str(row.get('source_system_name', '')),
                dest_system_name=str(row.get('dest_system_name', '')),
                source_ip=str(row.get('source_ip', '')),
                dest_ip=str(row.get('dest_ip', '')),
                service=str(row.get('service', '')),
                # 注: Policy.action 字段已在 commit 229b08b spec 重写中删除 (spec §1 不再要 action 列)
                usage_time=str(row.get('使用时间', '')) or str(row.get('usage_time', ''))
            )

            if policy.source_ip and policy.dest_ip:
                try:
                    matches = matcher.match_by_policy_context(policy)
                    if matches:
                        policy.firewall_id = matches[0]['firewall_id']
                        policy.device_source_zone = matches[0]['device_source_zone']
                        policy.device_dest_zone = matches[0]['device_dest_zone']
                except Exception as e:
                    logger.warning(f"防火墙严格资产匹配异常: {e}")

            db.add(policy)

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
    db.flush()  # 触发 FK 检查, 避免 commit 后才发现被引用

    # 清 user_modified 快照里对应条目 (PolicyVersion.data.policies 是个 list[dict])
    # 注: data 是 JSON/JSONB 列, SQLAlchemy 不会自动 track dict in-place 变更,
    #     用 sqlalchemy.orm.attributes.flag_modified 显式标记 dirty
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


FIELD_MAP = {
    '源端系统-环境-用途': 'source_system_name',
    '源IP': 'source_ip',
    '源安全域': 'device_source_zone',
    '目的端系统-环境-用途': 'dest_system_name',
    '目的IP': 'dest_ip',
    '目的安全域': 'device_dest_zone',
    '目的端口': 'service',
    '使用时间': 'usage_time',
}


@router.put("/{order_id}/policies")
def update_policies(order_id: int, policies_data: List[dict], db: Session = Depends(get_db)):
    """
    批量更新策略
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    try:
        actual_updated = 0
        matcher = FirewallMatcher(db)

        for policy_data in policies_data:
            policy_id = policy_data.get('id')
            if not policy_id: continue

            policy = db.query(Policy).filter(Policy.id == policy_id, Policy.order_id == order_id).first()
            if not policy: continue

            row_changed = False
            ip_changed = False

            for cn_key, value in policy_data.items():
                if cn_key == 'id': continue

                en_key = FIELD_MAP.get(cn_key)
                if en_key and hasattr(policy, en_key):
                    old_val = getattr(policy, en_key)
                    if str(old_val) != str(value):
                        setattr(policy, en_key, value)
                        row_changed = True
                        if en_key in ['source_ip', 'dest_ip']:
                            ip_changed = True

            if ip_changed and policy.source_ip and policy.dest_ip:
                try:
                    matches = matcher.match_by_policy_context(policy)
                    if matches:
                        policy.firewall_id = matches[0]['firewall_id']
                        policy.device_source_zone = matches[0]['device_source_zone']
                        policy.device_dest_zone = matches[0]['device_dest_zone']
                    else:
                        # 2026-06-23: 不清 firewall_id / device_*_zone (spec §1 强制 NOT NULL)
                        # spec 重写时这条 else 分支没联动改, 导致 PUT /policies 触发 NN 约束
                        # 失败. 真要解绑 firewall 走 DELETE firewall (C1 cascade 已支持),
                        # 不该在 update 流程里把必填字段清空
                        logger.warning(
                            f"策略 {policy.id} 更新后未匹配到 firewall, "
                            f"保留原 firewall_id={policy.firewall_id}, device_*_zone 不动"
                        )
                except Exception as match_err:
                    logger.warning(f"更新策略后执行严格重匹配失败: {match_err}")

            if row_changed:
                actual_updated += 1

        db.commit()

        # 生成并刷新修改快照
        all_policies = db.query(Policy).filter(Policy.order_id == order_id).all()
        policies_dict = [{
            'id': p.id,
            'source_system_name': p.source_system_name,
            'dest_system_name': p.dest_system_name,
            'source_ip': p.source_ip,
            'dest_ip': p.dest_ip,
            'service': p.service,
            # 'action' 字段已删: spec §1 不要 action 列, Policy ORM 不再持有此属性
            'firewall_id': p.firewall_id,
            'device_source_zone': p.device_source_zone,
            'device_dest_zone': p.device_dest_zone,
            '使用时间': p.usage_time or '',
        } for p in all_policies]

        db.query(PolicyVersion).filter(PolicyVersion.order_id == order_id,
                                       PolicyVersion.version_type == 'user_modified').delete()
        user_version = PolicyVersion(order_id=order_id, version_type='user_modified', data={'policies': policies_dict})
        db.add(user_version)
        db.commit()

        return {"message": "策略更新成功", "updated_count": actual_updated}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")