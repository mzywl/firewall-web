from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import uuid
from datetime import datetime

from app.database import get_db
from app.models import Order, Policy, OrderStatus, PolicyVersion
from app.schemas import OrderResponse, OrderCreate, PolicyResponse
from app.core.excel_parser import ExcelParser
from app.core.firewall_matcher import FirewallMatcher
from app.core.ip_formatter import IPFormatter

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
    # 验证文件类型
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="只支持 Excel 文件（.xlsx, .xls）")
    
    try:
        # 生成唯一文件名
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        # 保存文件
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # 解析 Excel
        parser = ExcelParser(file_path)
        excel_data = parser.parse()
        
        # 创建工单
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
        
        # 保存4个版本
        # 版本1：原始数据
        original_version = PolicyVersion(
            order_id=order.id,
            version_type='original',
            data={'policies': excel_data['original_data']}
        )
        db.add(original_version)
        
        # 版本2：第一次格式化（标准化字段名 + 格式化IP/端口）
        formatted_v1_version = PolicyVersion(
            order_id=order.id,
            version_type='formatted_v1',
            data={'policies': excel_data['formatted_v1_data']}
        )
        db.add(formatted_v1_version)
        
        # 版本3：第二次格式化（删除示例策略）
        formatted_v2_version = PolicyVersion(
            order_id=order.id,
            version_type='formatted_v2',
            data={'policies': excel_data['formatted_v2_data']}
        )
        db.add(formatted_v2_version)
        
        db.commit()

        # 解析策略数据（使用标准化后的英文字段名数据保存到 Policy 表）
        matcher = FirewallMatcher(db)
        for row in excel_data['data']:  # 改用 'data'，已经是英文字段名
            # 使用标准化后的英文字段名
            policy = Policy(
                order_id=order.id,
                source_zone=str(row.get('source_zone', '')),
                dest_zone=str(row.get('dest_zone', '')),
                source_ip=str(row.get('source_ip', '')),
                dest_ip=str(row.get('dest_ip', '')),
                service=str(row.get('service', '')),  # 强制转换为字符串
                action=str(row.get('action', 'permit'))
            )

            # 匹配防火墙
            dest_ip = row.get('dest_ip', '')
            if dest_ip:
                # 使用 IPFormatter 提取第一个 IP 地址
                first_ip = IPFormatter.extract_first_ip(dest_ip)

                # 只有当 IP 格式正确时才匹配防火墙
                if first_ip and '.' in first_ip:
                    try:
                        firewall_id = matcher.match_by_ip(first_ip)
                        policy.firewall_id = firewall_id
                    except Exception as e:
                        # 匹配失败不影响策略保存
                        pass

            db.add(policy)

        db.commit()

        # 返回包含版本数据的响应
        return {
            "id": order.id,
            "order_no": order.order_no,
            "title": order.title,
            "description": order.description,
            "status": order.status,
            "excel_file_path": order.excel_file_path,
            "created_by": order.created_by,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
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
    获取工单详情
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    return order


@router.get("/{order_id}/policies")
def get_order_policies(
    order_id: int, 
    version: str = None,
    db: Session = Depends(get_db)
):
    """
    获取工单的所有策略
    
    version 参数：
    - original: 用户上传的原始数据（只读，中文字段名）
    - formatted_v1: 第一次格式化后的数据（只读，中文字段名）
    - formatted_v2: 第二次格式化后的数据（只读，中文字段名）
    - user_modified: 用户手动编辑后的数据（可编辑）
    - 不传参数：返回 Policy 表中的当前策略（默认，英文字段名）
    
    特殊处理：
    - 如果请求 user_modified 但不存在，返回 Policy 表数据
    - 版本数据返回原始字典（保持中文字段名）
    - Policy 表数据返回 PolicyResponse 格式（英文字段名）
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    # 如果指定了版本，返回版本数据（原始字典，保持中文字段名）
    if version:
        policy_version = db.query(PolicyVersion).filter(
            PolicyVersion.order_id == order_id,
            PolicyVersion.version_type == version
        ).first()
        
        # 特殊处理：如果请求 user_modified 但不存在，返回 Policy 表数据
        if not policy_version and version == 'user_modified':
            policies = db.query(Policy).filter(Policy.order_id == order_id).all()
            return policies
        
        if not policy_version:
            raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")
        
        # 返回版本数据（原始字典，保持中文字段名）
        policies_data = policy_version.data.get('policies', [])
        result = []
        for idx, policy_dict in enumerate(policies_data):
            # 为每条策略添加必填字段（用于前端兼容）
            policy_response = {
                'id': idx + 1,  # 使用索引作为临时 ID（版本数据是只读的）
                'order_id': order_id,
                'is_merged': False,
                'created_at': policy_version.created_at.isoformat() if policy_version.created_at else datetime.now().isoformat(),
                **policy_dict  # 合并原始数据（保持中文字段名）
            }
            result.append(policy_response)
        return result
    
    # 默认返回 Policy 表中的当前策略（可编辑，转换为中文字段名）
    policies = db.query(Policy).filter(Policy.order_id == order_id).all()
    
    # 获取 formatted_v2 版本数据，用于补充"使用时间"字段
    formatted_v2_version = db.query(PolicyVersion).filter(
        PolicyVersion.order_id == order_id,
        PolicyVersion.version_type == 'formatted_v2'
    ).first()
    
    # 构建使用时间映射（通过行号匹配）
    usage_time_map = {}
    if formatted_v2_version:
        formatted_v2_data = formatted_v2_version.data.get('policies', [])
        for policy_dict in formatted_v2_data:
            row_number = policy_dict.get('_row_number')
            usage_time = policy_dict.get('使用时间', '')
            if row_number:
                usage_time_map[row_number] = usage_time
    
    # 将 Policy 对象转换为字典，并映射为中文字段名
    result = []
    for idx, policy in enumerate(policies):
        # 尝试通过索引匹配使用时间（假设顺序一致）
        usage_time = ''
        if formatted_v2_version:
            formatted_v2_data = formatted_v2_version.data.get('policies', [])
            if idx < len(formatted_v2_data):
                usage_time = formatted_v2_data[idx].get('使用时间', '')
        
        policy_dict = {
            'id': policy.id,
            'order_id': policy.order_id,
            'is_merged': policy.is_merged,
            'created_at': policy.created_at.isoformat() if policy.created_at else None,
            '源端系统-环境-用途': policy.source_zone or '',
            '源IP': policy.source_ip or '',
            '目的端系统-环境-用途': policy.dest_zone or '',
            '目的IP': policy.dest_ip or '',
            '目的端口': policy.service or '',
            '使用时间': usage_time,
        }
        result.append(policy_dict)
    
    return result


@router.get("/{order_id}/versions")
def get_order_versions(order_id: int, db: Session = Depends(get_db)):
    """
    获取工单的所有版本列表
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
def update_policies(
    order_id: int,
    policies_data: List[dict],
    db: Session = Depends(get_db)
):
    """
    批量更新策略
    自动保存 user_modified 版本
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    try:
        for policy_data in policies_data:
            policy_id = policy_data.get('id')
            if not policy_id:
                continue
            
            policy = db.query(Policy).filter(
                Policy.id == policy_id,
                Policy.order_id == order_id
            ).first()
            
            if policy:
                # 更新字段
                for key, value in policy_data.items():
                    if key != 'id' and hasattr(policy, key):
                        setattr(policy, key, value)
        
        db.commit()
        
        # 保存用户修改版本
        # 获取所有策略数据
        all_policies = db.query(Policy).filter(Policy.order_id == order_id).all()
        policies_dict = [
            {
                'id': p.id,
                'source_zone': p.source_zone,
                'dest_zone': p.dest_zone,
                'source_ip': p.source_ip,
                'dest_ip': p.dest_ip,
                'service': p.service,
                'action': p.action,
                'firewall_id': p.firewall_id
            }
            for p in all_policies
        ]
        
        # 删除旧的 user_modified 版本（如果存在）
        db.query(PolicyVersion).filter(
            PolicyVersion.order_id == order_id,
            PolicyVersion.version_type == 'user_modified'
        ).delete()
        
        # 创建新的 user_modified 版本
        user_version = PolicyVersion(
            order_id=order_id,
            version_type='user_modified',
            data={'policies': policies_dict}
        )
        db.add(user_version)
        db.commit()
        
        return {"message": "策略更新成功", "updated_count": len(policies_data)}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
