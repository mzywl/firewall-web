"""
区域访问配置API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.models import Firewall

router = APIRouter(prefix="/api/zone-access", tags=["zone-access"])


class ZoneAccessConfig(BaseModel):
    """区域访问配置"""
    source_zone: str
    dest_zone: str
    firewall_id: int
    nat_type: Optional[str] = None  # 'SNAT' | 'DNAT' | 'BOTH' | None


class ZoneAccessConfigCreate(BaseModel):
    """创建区域访问配置"""
    source_zone: str
    dest_zone: str
    firewall_id: int
    nat_type: Optional[str] = None


@router.get("/firewalls")
def get_firewalls(db: Session = Depends(get_db)):
    """
    获取所有防火墙列表（用于下拉选择）
    """
    firewalls = db.query(Firewall).filter(Firewall.is_active == 1).all()
    
    return {
        "firewalls": [
            {
                "id": fw.id,
                "name": fw.name,
                "alias": fw.alias,
                "type": fw.type,
                "region": fw.region,
                "zones": _extract_zones(fw)
            }
            for fw in firewalls
        ]
    }


@router.post("/analyze")
def analyze_zone_access(
    source_zone: str,
    dest_zone: str,
    db: Session = Depends(get_db)
):
    """
    分析区域访问场景
    
    根据源区域和目的区域，判断：
    1. 是否同区域（同一个防火墙的同一个区域）
    2. 推荐的防火墙
    3. 是否需要NAT
    """
    firewalls = db.query(Firewall).filter(Firewall.is_active == 1).all()
    
    # 查找包含源区域的防火墙
    source_firewalls = []
    for fw in firewalls:
        zones = _extract_zones(fw)
        if source_zone in zones:
            source_firewalls.append(fw)
    
    # 查找包含目的区域的防火墙
    dest_firewalls = []
    for fw in firewalls:
        zones = _extract_zones(fw)
        if dest_zone in zones:
            dest_firewalls.append(fw)
    
    # 判断是否同区域
    is_same_zone = False
    recommended_firewall = None
    need_nat = False
    nat_type = None
    
    # 检查是否在同一个防火墙的同一个区域
    for src_fw in source_firewalls:
        for dst_fw in dest_firewalls:
            if src_fw.id == dst_fw.id and source_zone == dest_zone:
                is_same_zone = True
                recommended_firewall = src_fw
                need_nat = False
                break
        if is_same_zone:
            break
    
    # 如果不是同区域，判断是否跨区域
    if not is_same_zone:
        # 检查是否在同一个防火墙的不同区域
        for src_fw in source_firewalls:
            for dst_fw in dest_firewalls:
                if src_fw.id == dst_fw.id:
                    recommended_firewall = src_fw
                    need_nat = True
                    nat_type = "SNAT"  # 默认出向需要SNAT
                    break
            if recommended_firewall:
                break
        
        # 如果不在同一个防火墙，推荐源防火墙
        if not recommended_firewall and source_firewalls:
            recommended_firewall = source_firewalls[0]
            need_nat = True
            nat_type = "SNAT"
    
    return {
        "source_zone": source_zone,
        "dest_zone": dest_zone,
        "is_same_zone": is_same_zone,
        "need_nat": need_nat,
        "nat_type": nat_type,
        "recommended_firewall": {
            "id": recommended_firewall.id,
            "name": recommended_firewall.name,
            "alias": recommended_firewall.alias,
            "region": recommended_firewall.region
        } if recommended_firewall else None,
        "source_firewalls": [
            {
                "id": fw.id,
                "name": fw.name,
                "alias": fw.alias
            }
            for fw in source_firewalls
        ],
        "dest_firewalls": [
            {
                "id": fw.id,
                "name": fw.name,
                "alias": fw.alias
            }
            for fw in dest_firewalls
        ]
    }


@router.post("/save")
def save_zone_access_config(
    config: ZoneAccessConfigCreate,
    db: Session = Depends(get_db)
):
    """
    保存区域访问配置
    """
    from app.models import ZoneAccessConfig
    
    # 检查是否已存在相同配置
    existing = db.query(ZoneAccessConfig).filter(
        ZoneAccessConfig.source_zone == config.source_zone,
        ZoneAccessConfig.dest_zone == config.dest_zone,
        ZoneAccessConfig.firewall_id == config.firewall_id
    ).first()
    
    if existing:
        # 更新现有配置
        existing.nat_type = config.nat_type
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        
        return {
            "message": "配置已更新",
            "config": {
                "id": existing.id,
                "source_zone": existing.source_zone,
                "dest_zone": existing.dest_zone,
                "firewall_id": existing.firewall_id,
                "nat_type": existing.nat_type,
                "created_at": existing.created_at.isoformat(),
                "updated_at": existing.updated_at.isoformat()
            }
        }
    else:
        # 创建新配置
        new_config = ZoneAccessConfig(
            source_zone=config.source_zone,
            dest_zone=config.dest_zone,
            firewall_id=config.firewall_id,
            nat_type=config.nat_type
        )
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
        
        return {
            "message": "配置已保存",
            "config": {
                "id": new_config.id,
                "source_zone": new_config.source_zone,
                "dest_zone": new_config.dest_zone,
                "firewall_id": new_config.firewall_id,
                "nat_type": new_config.nat_type,
                "created_at": new_config.created_at.isoformat(),
                "updated_at": new_config.updated_at.isoformat()
            }
        }


@router.get("/configs")
def list_zone_access_configs(db: Session = Depends(get_db)):
    """
    获取所有区域访问配置
    """
    from app.models import ZoneAccessConfig
    
    configs = db.query(ZoneAccessConfig).all()
    
    return {
        "configs": [
            {
                "id": cfg.id,
                "source_zone": cfg.source_zone,
                "dest_zone": cfg.dest_zone,
                "firewall_id": cfg.firewall_id,
                "firewall_name": cfg.firewall.name if cfg.firewall else None,
                "nat_type": cfg.nat_type,
                "created_at": cfg.created_at.isoformat(),
                "updated_at": cfg.updated_at.isoformat()
            }
            for cfg in configs
        ]
    }


@router.delete("/configs/{config_id}")
def delete_zone_access_config(config_id: int, db: Session = Depends(get_db)):
    """
    删除区域访问配置
    """
    from app.models import ZoneAccessConfig
    
    config = db.query(ZoneAccessConfig).filter(ZoneAccessConfig.id == config_id).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    db.delete(config)
    db.commit()
    
    return {"message": "配置已删除"}


def _extract_zones(firewall: Firewall) -> List[str]:
    """
    从防火墙配置中提取区域列表
    
    目前从 region 字段提取，未来可以扩展到专门的区域配置表
    """
    zones = []
    
    # 从 region 字段提取
    if firewall.region:
        zones.append(firewall.region)
    
    # TODO: 未来可以从专门的区域配置表中提取
    # 例如：firewall.zones 关联表
    
    return zones
