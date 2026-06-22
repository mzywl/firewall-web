from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Firewall
from app.schemas import FirewallCreate, FirewallUpdate, FirewallResponse
import base64

router = APIRouter(prefix="/api/firewalls", tags=["firewalls"])


def encrypt_password(password: str) -> str:
    """简单的密码加密（base64）"""
    if not password:
        return ""
    return base64.b64encode(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """简单的密码解密（base64）"""
    if not encrypted:
        return ""
    try:
        return base64.b64decode(encrypted.encode()).decode()
    except:
        return encrypted


@router.get("", response_model=List[FirewallResponse])
def list_firewalls(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    type: str = None,
    db: Session = Depends(get_db)
):
    """获取防火墙列表"""
    query = db.query(Firewall)
    
    if status:
        query = query.filter(Firewall.status == status)
    if type:
        query = query.filter(Firewall.type == type)
    
    firewalls = query.offset(skip).limit(limit).all()
    return firewalls


@router.get("/{firewall_id}", response_model=FirewallResponse)
def get_firewall(firewall_id: int, db: Session = Depends(get_db)):
    """获取单个防火墙详情"""
    firewall = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not firewall:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    return firewall


@router.post("", response_model=FirewallResponse, status_code=status.HTTP_201_CREATED)
def create_firewall(firewall: FirewallCreate, db: Session = Depends(get_db)):
    """创建防火墙"""
    # 处理连接配置中的密码加密
    connection_config = firewall.connection_config or {}
    if connection_config.get("password"):
        connection_config["password"] = encrypt_password(connection_config["password"])
    
    db_firewall = Firewall(
        name=firewall.name,
        alias=firewall.alias,
        type=firewall.type,
        management_ip=firewall.management_ip,
        # 新设计 (2026-06-22): region → belong_region,
        # covered_region/local_zone_name/external_zone_name/internal_protected_ips/
        # external_protected_ips/supported_policy_types/outbound_snat_pool/
        # inbound_snat_pool/push_contact/push_remark/remark 全部删除
        belong_region=firewall.belong_region,
        is_zone_boundary=firewall.is_zone_boundary,
        connection_type=firewall.connection_type,
        connection_config=connection_config,
        auto_push=firewall.auto_push,
        status=firewall.status,
    )
    
    db.add(db_firewall)
    db.commit()
    db.refresh(db_firewall)
    return db_firewall


@router.put("/{firewall_id}", response_model=FirewallResponse)
def update_firewall(
    firewall_id: int,
    firewall: FirewallUpdate,
    db: Session = Depends(get_db)
):
    """更新防火墙"""
    db_firewall = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not db_firewall:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    
    update_data = firewall.dict(exclude_unset=True)
    
    # 处理连接配置中的密码加密
    if "connection_config" in update_data and update_data["connection_config"]:
        connection_config = update_data["connection_config"]
        if connection_config.get("password"):
            connection_config["password"] = encrypt_password(connection_config["password"])
    
    for field, value in update_data.items():
        setattr(db_firewall, field, value)
    
    db.commit()
    db.refresh(db_firewall)
    return db_firewall


@router.delete("/{firewall_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_firewall(firewall_id: int, db: Session = Depends(get_db)):
    """删除防火墙（级联删除关联的策略）"""
    from app.models import Policy
    
    db_firewall = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not db_firewall:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    
    # 先删除关联的策略
    db.query(Policy).filter(Policy.firewall_id == firewall_id).delete()
    
    # 再删除防火墙
    db.delete(db_firewall)
    db.commit()
    return None
