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
    name: str = Field(..., max_length=100)
    type: FirewallType
    host: str = Field(..., max_length=100)
    port: int = Field(default=22)
    username: Optional[str] = None


class FirewallCreate(FirewallBase):
    password: Optional[str] = None
    config: Optional[dict] = None


class FirewallUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[int] = None


class FirewallResponse(FirewallBase):
    id: int
    is_active: int
    created_at: datetime

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
