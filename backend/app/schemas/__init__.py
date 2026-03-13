from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class OrderStatus(str, Enum):
    """工单状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FirewallType(str, Enum):
    """防火墙类型"""
    FORTIGATE = "fortigate"
    HILLSTONE = "hillstone"
    LEADSEC = "leadsec"
    H3C = "h3c"
    GUANQUN = "guanqun"
    FEITA = "feita"
    WANGSHEN = "wangshen"
    SANGFOR = "sangfor"
    HUAWEI = "huawei"
    SHANSHI = "shanshi"
    OTHER = "other"


class ConnectionType(str, Enum):
    """连接方式"""
    SSH = "ssh"
    API = "api"
    CLI = "cli"
    MANUAL = "manual"


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
    connection_type: ConnectionType = Field(default=ConnectionType.SSH)
    connection_config: Optional[dict] = None
    
    # 防护范围（分内部和外部）
    internal_protected_ips: Optional[str] = None
    external_protected_ips: Optional[str] = None
    supported_policy_types: Optional[List[str]] = None
    
    # NAT配置
    outbound_snat_pool: Optional[str] = None
    inbound_dnat_pool: Optional[str] = None
    inbound_snat_pool: Optional[str] = None
    outbound_dnat_pool: Optional[str] = None
    
    # 推送配置
    auto_push: int = Field(default=1)
    push_contact: Optional[str] = None
    push_remark: Optional[str] = None
    status: str = Field(default="enabled")
    remark: Optional[str] = None


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
    supported_policy_types: Optional[List[str]] = None
    
    outbound_snat_pool: Optional[str] = None
    inbound_dnat_pool: Optional[str] = None
    inbound_snat_pool: Optional[str] = None
    outbound_dnat_pool: Optional[str] = None
    
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
