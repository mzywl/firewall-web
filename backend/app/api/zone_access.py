"""
区域访问配置 API — 对齐 重构.md §1 新设计

新设计 (2026-06-22):
  - ZoneAccessConfig.source_zone → source_region
  - ZoneAccessConfig.dest_zone → dest_region
  - 新增 boundary_source_zone / boundary_dest_zone / need_nat / snat_pool (4 字段)
  - Firewall.region → belong_region
  - Firewall 不再有 local_zone_name / external_zone_name
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.models import Firewall, ZoneAccessConfig

router = APIRouter(prefix="/api/zone-access", tags=["zone-access"])


class ZoneAccessConfigBase(BaseModel):
    """区域访问配置基础模型 (对齐 spec 4 字段)"""
    source_region: str
    dest_region: str
    firewall_id: int
    boundary_source_zone: str
    boundary_dest_zone: str
    need_nat: int = 0
    snat_pool: str = None
    description: str = None


class ZoneAccessConfigCreate(ZoneAccessConfigBase):
    """创建区域访问配置"""
    pass


@router.get("/firewalls")
def get_firewalls(db: Session = Depends(get_db)):
    """获取所有防火墙列表 (用于下拉选择)"""
    firewalls = db.query(Firewall).filter(Firewall.is_active == 1).all()

    return {
        "firewalls": [
            {
                "id": fw.id,
                "name": fw.name,
                "alias": fw.alias,
                "type": fw.type,
                "belong_region": fw.belong_region,
                "zones": _extract_zones(fw),
            }
            for fw in firewalls
        ]
    }


@router.post("/analyze")
def analyze_zone_access(
    source_region: str,
    dest_region: str,
    db: Session = Depends(get_db),
):
    """
    分析区域访问场景
    """
    firewalls = db.query(Firewall).filter(Firewall.is_active == 1).all()

    # 找含 source_region 的防火墙 (通过 belong_region 或 firewall.zones[].connect_region)
    source_firewalls = []
    for fw in firewalls:
        if _firewall_in_region(fw, source_region):
            source_firewalls.append(fw)

    # 找含 dest_region 的防火墙
    dest_firewalls = []
    for fw in firewalls:
        if _firewall_in_region(fw, dest_region):
            dest_firewalls.append(fw)

    # 判断是否同区域
    is_same_zone = False
    recommended_firewall = None
    need_nat = False

    # 检查是否在同一个防火墙的同一个区域
    for src_fw in source_firewalls:
        for dst_fw in dest_firewalls:
            if src_fw.id == dst_fw.id and source_region == dest_region:
                is_same_zone = True
                recommended_firewall = src_fw
                need_nat = False
                break
        if is_same_zone:
            break

    # 如果不是同区域, 判断是否跨区域
    if not is_same_zone:
        for src_fw in source_firewalls:
            for dst_fw in dest_firewalls:
                if src_fw.id == dst_fw.id:
                    recommended_firewall = src_fw
                    need_nat = True  # 跨区域默认 SNAT
                    break
            if recommended_firewall:
                break

        if not recommended_firewall and source_firewalls:
            recommended_firewall = source_firewalls[0]
            need_nat = True  # 跨防火墙 = 跨区域

    # 找 cfg (按 boundary_* zones 匹配) 用于取 SNAT 池
    snat_pool = None
    if recommended_firewall:
        for cfg in (recommended_firewall.zone_access_configs or []):
            if cfg.source_region == source_region and cfg.dest_region == dest_region:
                snat_pool = cfg.snat_pool
                break

    return {
        "source_region": source_region,
        "dest_region": dest_region,
        "is_same_zone": is_same_zone,
        "need_nat": need_nat,
        "snat_pool": snat_pool,
        "recommended_firewall": {
            "id": recommended_firewall.id,
            "name": recommended_firewall.name,
            "alias": recommended_firewall.alias,
            "belong_region": recommended_firewall.belong_region,
        } if recommended_firewall else None,
        "source_firewalls": [
            {"id": fw.id, "name": fw.name, "alias": fw.alias}
            for fw in source_firewalls
        ],
        "dest_firewalls": [
            {"id": fw.id, "name": fw.name, "alias": fw.alias}
            for fw in dest_firewalls
        ],
    }


@router.post("/save")
def save_zone_access_config(
    config: ZoneAccessConfigCreate,
    db: Session = Depends(get_db),
):
    """保存区域访问配置 (对齐 spec 4 字段)"""
    # 检查是否已存在相同配置 (按 source_region + dest_region + firewall_id)
    existing = db.query(ZoneAccessConfig).filter(
        ZoneAccessConfig.source_region == config.source_region,
        ZoneAccessConfig.dest_region == config.dest_region,
        ZoneAccessConfig.firewall_id == config.firewall_id,
    ).first()

    if existing:
        # 更新现有配置
        existing.boundary_source_zone = config.boundary_source_zone
        existing.boundary_dest_zone = config.boundary_dest_zone
        existing.need_nat = config.need_nat
        existing.snat_pool = config.snat_pool
        existing.description = config.description
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)

        return {
            "message": "配置已更新",
            "config": {
                "id": existing.id,
                "source_region": existing.source_region,
                "dest_region": existing.dest_region,
                "boundary_source_zone": existing.boundary_source_zone,
                "boundary_dest_zone": existing.boundary_dest_zone,
                "need_nat": existing.need_nat,
                "snat_pool": existing.snat_pool,
                "firewall_id": existing.firewall_id,
                "created_at": existing.created_at.isoformat(),
                "updated_at": existing.updated_at.isoformat(),
            },
        }
    else:
        # 创建新配置
        new_config = ZoneAccessConfig(
            source_region=config.source_region,
            dest_region=config.dest_region,
            boundary_source_zone=config.boundary_source_zone,
            boundary_dest_zone=config.boundary_dest_zone,
            need_nat=config.need_nat,
            snat_pool=config.snat_pool,
            description=config.description,
            firewall_id=config.firewall_id,
        )
        db.add(new_config)
        db.commit()
        db.refresh(new_config)

        return {
            "message": "配置已保存",
            "config": {
                "id": new_config.id,
                "source_region": new_config.source_region,
                "dest_region": new_config.dest_region,
                "boundary_source_zone": new_config.boundary_source_zone,
                "boundary_dest_zone": new_config.boundary_dest_zone,
                "need_nat": new_config.need_nat,
                "snat_pool": new_config.snat_pool,
                "firewall_id": new_config.firewall_id,
                "created_at": new_config.created_at.isoformat(),
                "updated_at": new_config.updated_at.isoformat(),
            },
        }


@router.get("/configs")
def list_zone_access_configs(db: Session = Depends(get_db)):
    """获取所有区域访问配置 (对齐 spec)"""
    configs = db.query(ZoneAccessConfig).all()

    return {
        "configs": [
            {
                "id": cfg.id,
                "source_region": cfg.source_region,
                "dest_region": cfg.dest_region,
                "boundary_source_zone": cfg.boundary_source_zone,
                "boundary_dest_zone": cfg.boundary_dest_zone,
                "need_nat": cfg.need_nat,
                "snat_pool": cfg.snat_pool,
                "firewall_id": cfg.firewall_id,
                "firewall_name": cfg.firewall.name if cfg.firewall else None,
                "created_at": cfg.created_at.isoformat(),
                "updated_at": cfg.updated_at.isoformat(),
            }
            for cfg in configs
        ]
    }


@router.delete("/configs/{config_id}")
def delete_zone_access_config(config_id: int, db: Session = Depends(get_db)):
    """删除区域访问配置"""
    config = db.query(ZoneAccessConfig).filter(ZoneAccessConfig.id == config_id).first()

    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    db.delete(config)
    db.commit()

    return {"message": "配置已删除"}


def _firewall_in_region(fw: Firewall, region: str) -> bool:
    """判断 firewall 是否覆盖 region

    判定路径:
      1. fw.belong_region == region
      2. fw.zones 中某 zone.connect_region == region
    """
    if fw.belong_region == region:
        return True
    for zone in (fw.zones or []):
        if zone.connect_region == region:
            return True
    return False


def _extract_zones(fw: Firewall) -> List[str]:
    """从防火墙配置提取 zone 列表 (新设计: 不用 local/external_zone_name)"""
    zones = []

    # 1) belong_region
    if fw.belong_region:
        zones.append(fw.belong_region)

    # 2) firewall_zones 表 (zone_name + connect_region)
    for z in (fw.zones or []):
        if z.zone_name and z.zone_name not in zones:
            zones.append(z.zone_name)
        if z.connect_region and z.connect_region not in zones:
            zones.append(z.connect_region)

    return zones