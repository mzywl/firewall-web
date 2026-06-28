"""Pydantic schemas — 对齐 重构.md §1 spec

对应 models/__init__.py 的精简后字段集合。
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class OrderStatus(str, Enum):
    """工单状态"""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class FirewallType(str, Enum):
    """防火墙厂商类型 (重构.md §1 精简后)"""
    fortigate = "fortigate"
    huawei = "huawei"
    h3c = "h3c"
    hillstone = "hillstone"
    sangfor = "sangfor"
    other = "other"


class ConnectionType(str, Enum):
    """连接方式 (重构.md §1 只保留 ssh/api)"""
    ssh = "ssh"
    api = "api"


# ==========================================
# Order Schemas
# ==========================================
class OrderBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    created_by: Optional[str] = None


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[OrderStatus] = None


class OrderResponse(OrderBase):
    id: int
    order_no: str
    status: OrderStatus
    excel_file_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# Policy Schemas (对齐 spec 精简)
# ==========================================
class PolicyBase(BaseModel):
    """Policy 基础字段 (对齐 重构.md §1)"""
    source_system_name: Optional[str] = Field(None, max_length=100, description="源系统名(Excel 解析)")
    dest_system_name: Optional[str] = Field(None, max_length=100, description="目的系统名(Excel 解析)")
    source_ip: Optional[str] = Field(None, description="源 IP")
    dest_ip: Optional[str] = Field(None, description="目的 IP")
    service: Optional[str] = Field(None, description="服务/端口")
    usage_time: Optional[str] = Field(None, description="使用时间")

# --- Pydantic 模型 ---
class IgnorePlanRowRequest(BaseModel):
    row_uuid: str
    ignore: bool  # True 表示变灰(删除)，False 表示恢复

class PolicyCreate(PolicyBase):
    order_id: int
    firewall_id: int  # spec 强制 NN


class PolicyUpdate(BaseModel):
    """编辑工单时更新 Policy"""
    source_ip: Optional[str] = None
    dest_ip: Optional[str] = None
    service: Optional[str] = None
    usage_time: Optional[str] = None
    source_system_name: Optional[str] = None
    dest_system_name: Optional[str] = None
    device_source_zone: Optional[str] = None
    device_dest_zone: Optional[str] = None


class PolicyResponse(PolicyBase):
    """Policy 响应 (对齐 spec 字段)"""
    id: int
    order_id: int
    firewall_id: int
    device_source_zone: str
    device_dest_zone: str
    source_snat_ip: Optional[str] = None
    push_status: Optional[str] = None
    push_result: Optional[str] = None
    pushed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# Firewall Schemas (精简后)
# ==========================================
class FirewallBase(BaseModel):
    name: str = Field(..., max_length=200)
    alias: Optional[str] = Field(None, max_length=100)
    type: FirewallType
    management_ip: str = Field(..., max_length=50)

    belong_region: Optional[str] = Field(None, max_length=100, description="所属大区(组织归属)")
    is_zone_boundary: int = Field(default=0, description="是否区域边界防火墙")

    connection_type: ConnectionType = Field(default=ConnectionType.ssh)
    connection_config: Optional[dict] = None

    auto_push: int = Field(default=1)
    status: str = Field(default="enabled")
    is_active: int = Field(default=1)

    @validator('type', pre=True)
    def lowercase_type(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v

    @validator('connection_type', pre=True)
    def lowercase_connection_type(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v


class FirewallCreate(FirewallBase):
    pass


class FirewallUpdate(BaseModel):
    """更新防火墙 (spec 字段)"""
    name: Optional[str] = None
    alias: Optional[str] = None
    type: Optional[FirewallType] = None
    management_ip: Optional[str] = None

    belong_region: Optional[str] = None
    is_zone_boundary: Optional[int] = None

    connection_type: Optional[ConnectionType] = None
    connection_config: Optional[dict] = None

    auto_push: Optional[int] = None
    status: Optional[str] = None
    is_active: Optional[int] = None


class FirewallResponse(FirewallBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# FirewallZone Schemas
# ==========================================
class FirewallZoneBase(BaseModel):
    firewall_id: int
    zone_name: str = Field(..., max_length=100)
    protected_ips: Optional[str] = None
    connect_region: str = Field(..., max_length=100, description="安全域连接的大区")


class FirewallZoneCreate(FirewallZoneBase):
    pass


class FirewallZoneUpdate(BaseModel):
    zone_name: Optional[str] = None
    protected_ips: Optional[str] = None
    connect_region: Optional[str] = None


class FirewallZoneResponse(FirewallZoneBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# ZoneAccessConfig Schemas (新字段对齐 spec)
# ==========================================
class ZoneAccessConfigBase(BaseModel):
    firewall_id: int = Field(..., description="扼守此大区通道的边界防火墙ID")
    source_region: str = Field(..., max_length=100, description="源宏观大区名称")
    dest_region: str = Field(..., max_length=100, description="目的宏观大区名称")
    boundary_source_zone: str = Field(..., max_length=100, description="边界墙面向源大区的本地 Zone 名称")
    boundary_dest_zone: str = Field(..., max_length=100, description="边界墙面向目的大区的本地 Zone 名称")
    need_nat: int = Field(default=0, description="此跨区路径是否强制 SNAT")
    snat_pool: Optional[str] = Field(None, max_length=500, description="SNAT 地址池")
    description: Optional[str] = None


class ZoneAccessConfigCreate(ZoneAccessConfigBase):
    pass


class ZoneAccessConfigUpdate(BaseModel):
    source_region: Optional[str] = None
    dest_region: Optional[str] = None
    boundary_source_zone: Optional[str] = None
    boundary_dest_zone: Optional[str] = None
    need_nat: Optional[int] = None
    snat_pool: Optional[str] = None
    description: Optional[str] = None


class ZoneAccessConfigResponse(ZoneAccessConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# PolicyVersion Schemas
# ==========================================
class PolicyVersionCreate(BaseModel):
    order_id: int
    version_type: str  # 'original', 'formatted', 'user_modified'
    data: dict


class PolicyVersionResponse(BaseModel):
    id: int
    order_id: int
    version_type: str
    data: dict
    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# PushLog / PushSnapshot (新增 spec 字段)
# ==========================================
class PushLogResponse(BaseModel):
    id: int
    snapshot_id: int
    seq: int
    stage: str
    level: str
    message: str
    data_json: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True