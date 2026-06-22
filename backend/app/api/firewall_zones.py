"""
防火墙区域管理 API — 对齐 重构.md §1 + 设计文档 §1

新设计 (2026-06-22):
  - 删除 ZoneAccessRule 表 (spec 不要)
  - FirewallZone 新增 connect_region 字段 (替代 description)
  - FirewallZone.description 字段已删

进一步对齐设计文档 (2026-06-22):
  - FirewallZone 新增 zone_role 字段 (internal/external 显式角色)
  - 替代旧隐式判定 connect_region == fw.belong_region
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from app.database import get_db
from app.models import Firewall, FirewallZone

router = APIRouter(prefix="/api/firewall-zones", tags=["firewall-zones"])


# 设计文档 §1: 显式 enum
ZONE_ROLE_INTERNAL = "internal"  # 内部防护域 (Trust)
ZONE_ROLE_EXTERNAL = "external"  # 外部防护域 (Untrust, 通往其他墙/大区)


class FirewallZoneCreate(BaseModel):
    """创建防火墙区域 (设计文档 §1: zone_role 显式标记)"""
    firewall_id: int
    zone_name: str
    protected_ips: Optional[str] = None
    connect_region: str  # spec 要求 NOT NULL
    zone_role: str = Field(default=ZONE_ROLE_INTERNAL, description="internal=内部防护, external=外部防护")


class FirewallZoneUpdate(BaseModel):
    """更新防火墙区域"""
    zone_name: Optional[str] = None
    protected_ips: Optional[str] = None
    connect_region: Optional[str] = None
    zone_role: Optional[str] = None


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
                "zone_role": zone.zone_role,  # 设计文档 §1: 显式角色
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

    if zone.zone_role not in (ZONE_ROLE_INTERNAL, ZONE_ROLE_EXTERNAL):
        raise HTTPException(status_code=400, detail=f"zone_role 必须是 {ZONE_ROLE_INTERNAL} 或 {ZONE_ROLE_EXTERNAL}")

    # 设计文档 §9 允许多个同名 zone (e.g. fw1 同时有 2 个 "Untrust" zone, 分别连不同大区)
    # 唯一性按 (firewall_id, zone_name, connect_region) 复合键判
    # 也就是说: 同名 + 同 connect_region → 视为真重复 (用户误操作)
    # 同名 + 不同 connect_region → 合法 (设计文档 §9 多接口场景)
    existing = db.query(FirewallZone).filter(
        FirewallZone.firewall_id == zone.firewall_id,
        FirewallZone.zone_name == zone.zone_name,
        FirewallZone.connect_region == zone.connect_region,
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"该防火墙已存在同名 + 同 connect_region 的区域 (zone_name='{zone.zone_name}', connect_region='{zone.connect_region}')",
        )

    new_zone = FirewallZone(
        firewall_id=zone.firewall_id,
        zone_name=zone.zone_name,
        protected_ips=zone.protected_ips,
        connect_region=zone.connect_region,
        zone_role=zone.zone_role,
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
        "zone_role": new_zone.zone_role,
        "created_at": new_zone.created_at.isoformat(),
    }


@router.put("/{zone_id}")
def update_firewall_zone(zone_id: int, zone: FirewallZoneUpdate, db: Session = Depends(get_db)):
    """更新防火墙区域"""
    db_zone = db.query(FirewallZone).filter(FirewallZone.id == zone_id).first()
    if not db_zone:
        raise HTTPException(status_code=404, detail="区域不存在")

    update_data = zone.dict(exclude_unset=True)
    if "zone_role" in update_data and update_data["zone_role"] not in (ZONE_ROLE_INTERNAL, ZONE_ROLE_EXTERNAL):
        raise HTTPException(status_code=400, detail=f"zone_role 必须是 {ZONE_ROLE_INTERNAL} 或 {ZONE_ROLE_EXTERNAL}")

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
        "zone_role": db_zone.zone_role,
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