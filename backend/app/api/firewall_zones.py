"""
防火墙区域管理API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.models import Firewall, FirewallZone, ZoneAccessRule

router = APIRouter(prefix="/api/firewall-zones", tags=["firewall-zones"])


class FirewallZoneCreate(BaseModel):
    """创建防火墙区域"""
    firewall_id: int
    zone_name: str
    protected_ips: Optional[str] = None
    description: Optional[str] = None


class FirewallZoneUpdate(BaseModel):
    """更新防火墙区域"""
    zone_name: Optional[str] = None
    protected_ips: Optional[str] = None
    description: Optional[str] = None


class ZoneAccessRuleCreate(BaseModel):
    """创建区域访问规则"""
    source_zone_id: int
    dest_zone_id: int
    firewall_id: int
    allow_access: int = 1
    nat_type: Optional[str] = None
    description: Optional[str] = None


@router.get("/firewall/{firewall_id}")
def get_firewall_zones(firewall_id: int, db: Session = Depends(get_db)):
    """
    获取指定防火墙的所有区域
    """
    firewall = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not firewall:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    
    zones = db.query(FirewallZone).filter(FirewallZone.firewall_id == firewall_id).all()
    
    return {
        "firewall": {
            "id": firewall.id,
            "name": firewall.name,
            "alias": firewall.alias
        },
        "zones": [
            {
                "id": zone.id,
                "zone_name": zone.zone_name,
                "protected_ips": zone.protected_ips,
                "description": zone.description,
                "created_at": zone.created_at.isoformat(),
                "updated_at": zone.updated_at.isoformat()
            }
            for zone in zones
        ]
    }


@router.post("/")
def create_firewall_zone(zone: FirewallZoneCreate, db: Session = Depends(get_db)):
    """
    创建防火墙区域
    """
    # 检查防火墙是否存在
    firewall = db.query(Firewall).filter(Firewall.id == zone.firewall_id).first()
    if not firewall:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    
    # 检查区域名称是否重复
    existing = db.query(FirewallZone).filter(
        FirewallZone.firewall_id == zone.firewall_id,
        FirewallZone.zone_name == zone.zone_name
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="该防火墙已存在同名区域")
    
    # 创建区域
    new_zone = FirewallZone(
        firewall_id=zone.firewall_id,
        zone_name=zone.zone_name,
        protected_ips=zone.protected_ips,
        description=zone.description
    )
    
    db.add(new_zone)
    db.commit()
    db.refresh(new_zone)
    
    return {
        "message": "区域创建成功",
        "zone": {
            "id": new_zone.id,
            "firewall_id": new_zone.firewall_id,
            "zone_name": new_zone.zone_name,
            "protected_ips": new_zone.protected_ips,
            "description": new_zone.description
        }
    }


@router.put("/{zone_id}")
def update_firewall_zone(
    zone_id: int,
    zone_update: FirewallZoneUpdate,
    db: Session = Depends(get_db)
):
    """
    更新防火墙区域
    """
    zone = db.query(FirewallZone).filter(FirewallZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="区域不存在")
    
    # 更新字段
    if zone_update.zone_name is not None:
        zone.zone_name = zone_update.zone_name
    if zone_update.protected_ips is not None:
        zone.protected_ips = zone_update.protected_ips
    if zone_update.description is not None:
        zone.description = zone_update.description
    
    zone.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(zone)
    
    return {
        "message": "区域更新成功",
        "zone": {
            "id": zone.id,
            "zone_name": zone.zone_name,
            "protected_ips": zone.protected_ips,
            "description": zone.description
        }
    }


@router.delete("/{zone_id}")
def delete_firewall_zone(zone_id: int, db: Session = Depends(get_db)):
    """
    删除防火墙区域
    """
    zone = db.query(FirewallZone).filter(FirewallZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="区域不存在")
    
    db.delete(zone)
    db.commit()
    
    return {"message": "区域删除成功"}


@router.get("/{zone_id}/access-rules")
def get_zone_access_rules(zone_id: int, db: Session = Depends(get_db)):
    """
    获取指定区域的访问规则
    """
    zone = db.query(FirewallZone).filter(FirewallZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="区域不存在")
    
    # 获取源区域为该区域的规则
    outbound_rules = db.query(ZoneAccessRule).filter(
        ZoneAccessRule.source_zone_id == zone_id
    ).all()
    
    # 获取目的区域为该区域的规则
    inbound_rules = db.query(ZoneAccessRule).filter(
        ZoneAccessRule.dest_zone_id == zone_id
    ).all()
    
    return {
        "zone": {
            "id": zone.id,
            "zone_name": zone.zone_name
        },
        "outbound_rules": [
            {
                "id": rule.id,
                "dest_zone": {
                    "id": rule.dest_zone.id,
                    "zone_name": rule.dest_zone.zone_name
                },
                "allow_access": rule.allow_access,
                "nat_type": rule.nat_type,
                "description": rule.description
            }
            for rule in outbound_rules
        ],
        "inbound_rules": [
            {
                "id": rule.id,
                "source_zone": {
                    "id": rule.source_zone.id,
                    "zone_name": rule.source_zone.zone_name
                },
                "allow_access": rule.allow_access,
                "nat_type": rule.nat_type,
                "description": rule.description
            }
            for rule in inbound_rules
        ]
    }


@router.post("/access-rules")
def create_zone_access_rule(rule: ZoneAccessRuleCreate, db: Session = Depends(get_db)):
    """
    创建区域访问规则
    """
    # 检查源区域和目的区域是否存在
    source_zone = db.query(FirewallZone).filter(FirewallZone.id == rule.source_zone_id).first()
    dest_zone = db.query(FirewallZone).filter(FirewallZone.id == rule.dest_zone_id).first()
    
    if not source_zone or not dest_zone:
        raise HTTPException(status_code=404, detail="源区域或目的区域不存在")
    
    # 检查是否已存在相同规则
    existing = db.query(ZoneAccessRule).filter(
        ZoneAccessRule.source_zone_id == rule.source_zone_id,
        ZoneAccessRule.dest_zone_id == rule.dest_zone_id,
        ZoneAccessRule.firewall_id == rule.firewall_id
    ).first()
    
    if existing:
        # 更新现有规则
        existing.allow_access = rule.allow_access
        existing.nat_type = rule.nat_type
        existing.description = rule.description
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        
        return {
            "message": "规则已更新",
            "rule": {
                "id": existing.id,
                "source_zone_id": existing.source_zone_id,
                "dest_zone_id": existing.dest_zone_id,
                "allow_access": existing.allow_access,
                "nat_type": existing.nat_type
            }
        }
    else:
        # 创建新规则
        new_rule = ZoneAccessRule(
            source_zone_id=rule.source_zone_id,
            dest_zone_id=rule.dest_zone_id,
            firewall_id=rule.firewall_id,
            allow_access=rule.allow_access,
            nat_type=rule.nat_type,
            description=rule.description
        )
        
        db.add(new_rule)
        db.commit()
        db.refresh(new_rule)
        
        return {
            "message": "规则创建成功",
            "rule": {
                "id": new_rule.id,
                "source_zone_id": new_rule.source_zone_id,
                "dest_zone_id": new_rule.dest_zone_id,
                "allow_access": new_rule.allow_access,
                "nat_type": new_rule.nat_type
            }
        }


@router.delete("/access-rules/{rule_id}")
def delete_zone_access_rule(rule_id: int, db: Session = Depends(get_db)):
    """
    删除区域访问规则
    """
    rule = db.query(ZoneAccessRule).filter(ZoneAccessRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    
    db.delete(rule)
    db.commit()
    
    return {"message": "规则删除成功"}
