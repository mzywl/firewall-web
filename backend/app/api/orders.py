from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import uuid
from datetime import datetime

from app.database import get_db
from app.models import Order, Policy, OrderStatus
from app.schemas import OrderResponse, OrderCreate, PolicyResponse
from app.core.excel_parser import ExcelParser
from app.core.firewall_matcher import FirewallMatcher

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
            status=OrderStatus.PENDING,
            created_by=created_by
        )
        
        db.add(order)
        db.commit()
        db.refresh(order)
        
        # 解析策略数据
        matcher = FirewallMatcher(db)
        for row in excel_data['data']:
            policy = Policy(
                order_id=order.id,
                source_zone=row.get('源区域', ''),
                dest_zone=row.get('目标区域', ''),
                source_ip=row.get('源IP', ''),
                dest_ip=row.get('目标IP', ''),
                service=row.get('服务', ''),
                action=row.get('动作', 'permit')
            )
            
            # 匹配防火墙
            dest_ip = row.get('目标IP', '')
            if dest_ip:
                firewall_id = matcher.match_by_ip(dest_ip.split('/')[0].split('-')[0])
                policy.firewall_id = firewall_id
            
            db.add(policy)
        
        db.commit()
        
        return order
        
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


@router.get("/{order_id}/policies", response_model=List[PolicyResponse])
def get_order_policies(order_id: int, db: Session = Depends(get_db)):
    """
    获取工单的所有策略
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    policies = db.query(Policy).filter(Policy.order_id == order_id).all()
    return policies


@router.put("/{order_id}/policies")
def update_policies(
    order_id: int,
    policies_data: List[dict],
    db: Session = Depends(get_db)
):
    """
    批量更新策略
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
        return {"message": "策略更新成功", "updated_count": len(policies_data)}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
