"""
防火墙区域管理 API — 对齐 重构.md §1 新设计

新设计 (2026-06-22):
  - 删除 ZoneAccessRule 表 (spec 不要)
  - FirewallZone 新增 connect_region 字段 (替代 description)
  - FirewallZone.description 字段已删
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.models import Firewall, FirewallZone

router = APIRouter(prefix="/api/firewall-zones", tags=["firewall-zones"])


class FirewallZoneCreate(BaseModel):
    """创建防火墙区域 (新设计: description → connect_region)"""
    firewall_id: int
    zone_name: str
    protected_ips: Optional[str] = None
    connect_region: str  # spec 要求 NOT NULL


class FirewallZoneUpdate(BaseModel):
    """更新防火墙区域"""
    zone_name: Optional[str] = None
    protected_ips: Optional[str] = None
    connect_region: Optional[str] = None


@router.get("/firewall/{firewall_id}")
def get_firewall_zones(firewall_id: int, db: Session = Depends(get_db)):
    """获取指定防火墙的所有区域"""
    firewall = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not firewall:
        raise HTTPException(status_code=404, detail="防火墙不存在")

    zones = db.query(FirewallZone).filter(FirewallZone.firewall_id == firewall_id).all()

    return {
        "firewall": {
            "id": firewall.id,
            "name": firewall.name,
            "alias": firewall.alias,
            "belong_region": firewall.belong_region,  # 新设计: region → belong_region
        },
        "zones": [
            {
                "id": zone.id,
                "zone_name": zone.zone_name,
                "protected_ips": zone.protected_ips,
                "connect_region": zone.connect_region,
                "created_at": zone.created_at.isoformat(),
                "updated_at": zone.updated_at.isoformat(),
            }
            for zone in zones
        ],
    }


@router.post("/")
def create_firewall_zone(zone: FirewallZoneCreate, db: Session = Depends(get_db)):
    """创建防火墙区域"""
    firewall = db.query(Firewall).filter(Firewall.id == zone.firewall_id).first()
    if not firewall:
        raise HTTPException(status_code=404, detail="防火墙不存在")

    existing = db.query(FirewallZone).filter(
        FirewallZone.firewall_id == zone.firewall_id,
        FirewallZone.zone_name == zone.zone_name,
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="该防火墙已存在同名区域")

    new_zone = FirewallZone(
        firewall_id=zone.firewall_id,
        zone_name=zone.zone_name,
        protected_ips=zone.protected_ips,
        connect_region=zone.connect_region,
    )

    db.add(new_zone)
    db.commit()
    db.refresh(new_zone)

    return {
        "id": new_zone.id,
        "firewall_id": new_zone.firewall_id,
        "zone_name": new_zone.zone_name,
        "protected_ips": new_zone.protected_ips,
        "connect_region": new_zone.connect_region,
        "created_at": new_zone.created_at.isoformat(),
    }


@router.put("/{zone_id}")
def update_firewall_zone(zone_id: int, zone: FirewallZoneUpdate, db: Session = Depends(get_db)):
    """更新防火墙区域"""
    db_zone = db.query(FirewallZone).filter(FirewallZone.id == zone_id).first()
    if not db_zone:
        raise HTTPException(status_code=404, detail="区域不存在")

    update_data = zone.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_zone, field, value)

    db_zone.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_zone)

    return {
        "id": db_zone.id,
        "firewall_id": db_zone.firewall_id,
        "zone_name": db_zone.zone_name,
        "protected_ips": db_zone.protected_ips,
        "connect_region": db_zone.connect_region,
        "updated_at": db_zone.updated_at.isoformat(),
    }


@router.delete("/{zone_id}", status_code=204)
def delete_firewall_zone(zone_id: int, db: Session = Depends(get_db)):
    """删除防火墙区域"""
    db_zone = db.query(FirewallZone).filter(FirewallZone.id == zone_id).first()
    if not db_zone:
        raise HTTPException(status_code=404, detail="区域不存在")

    db.delete(db_zone)
    db.commit()
    return None


# ==========================================
# ZoneAccessRule 已删除 (spec 不要), 跨区域规则改用 ZoneAccessConfig
# 详见 backend/app/api/zone_access.py
# ==========================================