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
    """防火墙类型"""
    fortigate = "fortigate"
    hillstone = "hillstone"
    leadsec = "leadsec"
    h3c = "h3c"
    guanqun = "guanqun"
    feita = "feita"
    wangshen = "wangshen"
    sangfor = "sangfor"
    huawei = "huawei"
    shanshi = "shanshi"
    other = "other"


class ConnectionType(str, Enum):
    """连接方式"""
    ssh = "ssh"
    api = "api"
    cli = "cli"
    manual = "manual"


# Order Schemas
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


# Policy Schemas
class PolicyBase(BaseModel):
    source_zone: Optional[str] = None
    dest_zone: Optional[str] = None
    source_ip: Optional[str] = None
    dest_ip: Optional[str] = None
    service: Optional[str] = None
    action: Optional[str] = None


class PolicyCreate(PolicyBase):
    order_id: int
    firewall_id: Optional[int] = None


class PolicyResponse(PolicyBase):
    id: int
    order_id: int
    firewall_id: Optional[int] = None
    is_merged: int
    push_status: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Firewall Schemas
class FirewallBase(BaseModel):
    name: str = Field(..., max_length=200)
    alias: Optional[str] = Field(None, max_length=100)
    type: FirewallType
    management_ip: str = Field(..., max_length=50)
    
    # 区域信息
    region: Optional[str] = Field(None, max_length=100)
    local_zone_name: Optional[str] = Field(None, max_length=100)
    external_zone_name: Optional[str] = Field(None, max_length=100)
    
    # 连接方式
    connection_type: ConnectionType = Field(default=ConnectionType.ssh)
    connection_config: Optional[dict] = None
    
    # 防护范围（分内部和外部）
    internal_protected_ips: Optional[str] = None
    external_protected_ips: Optional[str] = None
    is_zone_boundary: int = Field(default=0, description="是否区域边界防火墙(0:否, 1:是)；仅边界防火墙需配 NAT 地址池")
    # supported_policy_types 已废弃（UI 隐藏），保留字段以兼容旧数据
    supported_policy_types: Optional[List[str]] = None

    # SNAT 地址池（仅当 is_zone_boundary=1 时由 UI 显示和填写）
    # 项目已决定不再分析 DNAT，所以只保留 SNAT 相关字段
    outbound_snat_pool: Optional[str] = None
    inbound_snat_pool: Optional[str] = None
    
    # 推送配置
    auto_push: int = Field(default=1)
    push_contact: Optional[str] = None
    push_remark: Optional[str] = None
    status: str = Field(default="enabled")
    remark: Optional[str] = None
    
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
    name: Optional[str] = None
    alias: Optional[str] = None
    type: Optional[FirewallType] = None
    management_ip: Optional[str] = None
    
    region: Optional[str] = None
    local_zone_name: Optional[str] = None
    external_zone_name: Optional[str] = None
    
    connection_type: Optional[ConnectionType] = None
    connection_config: Optional[dict] = None
    
    internal_protected_ips: Optional[str] = None
    external_protected_ips: Optional[str] = None
    is_zone_boundary: Optional[int] = None
    supported_policy_types: Optional[List[str]] = None
    
    outbound_snat_pool: Optional[str] = None
    inbound_snat_pool: Optional[str] = None
    
    auto_push: Optional[int] = None
    push_contact: Optional[str] = None
    push_remark: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None
    is_active: Optional[int] = None


class FirewallResponse(FirewallBase):
    id: int
    is_active: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# OperationLog Schemas
class OperationLogCreate(BaseModel):
    order_id: Optional[int] = None
    operation_type: str
    operation_detail: Optional[str] = None
    operator: Optional[str] = None
    result: Optional[str] = None
    error_message: Optional[str] = None


class OperationLogResponse(OperationLogCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# PolicyVersion Schemas
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
