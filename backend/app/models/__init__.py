from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum


class OrderStatus(str, enum.Enum):
    """工单状态"""
    PENDING = "pending"  # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class FirewallType(str, enum.Enum):
    """防火墙类型"""
    FORTIGATE = "fortigate"
    HILLSTONE = "hillstone"
    LEADSEC = "leadsec"
    H3C = "h3c"


class Order(Base):
    """工单表"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String(50), unique=True, index=True, nullable=False, comment="工单编号")
    title = Column(String(200), nullable=False, comment="工单标题")
    description = Column(Text, comment="工单描述")
    excel_file_path = Column(String(500), comment="Excel文件路径")
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, comment="工单状态")
    created_by = Column(String(100), comment="创建人")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    policies = relationship("Policy", back_populates="order", cascade="all, delete-orphan")
    logs = relationship("OperationLog", back_populates="order", cascade="all, delete-orphan")


class Policy(Base):
    """策略表"""
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, comment="工单ID")
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), comment="防火墙ID")
    
    # 策略字段
    source_zone = Column(String(100), comment="源区域")
    dest_zone = Column(String(100), comment="目标区域")
    source_ip = Column(String(500), comment="源IP")
    dest_ip = Column(String(500), comment="目标IP")
    service = Column(String(500), comment="服务/端口")
    action = Column(String(50), comment="动作(permit/deny)")
    
    # 合并优化相关
    is_merged = Column(Integer, default=0, comment="是否已合并(0:否, 1:是)")
    merged_policy_id = Column(Integer, comment="合并后的策略ID")
    
    # 推送状态
    push_status = Column(String(50), comment="推送状态")
    push_result = Column(Text, comment="推送结果")
    pushed_at = Column(DateTime, comment="推送时间")
    
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    order = relationship("Order", back_populates="policies")
    firewall = relationship("Firewall")


class Firewall(Base):
    """防火墙配置表"""
    __tablename__ = "firewalls"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="防火墙名称")
    type = Column(Enum(FirewallType), nullable=False, comment="防火墙类型")
    host = Column(String(100), nullable=False, comment="主机地址")
    port = Column(Integer, default=22, comment="SSH端口")
    username = Column(String(100), comment="用户名")
    password = Column(String(200), comment="密码(加密存储)")
    
    # 防火墙特定配置
    config = Column(JSON, comment="其他配置(JSON格式)")
    
    is_active = Column(Integer, default=1, comment="是否启用(0:否, 1:是)")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class OperationLog(Base):
    """操作日志表"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), comment="工单ID")
    operation_type = Column(String(50), nullable=False, comment="操作类型")
    operation_detail = Column(Text, comment="操作详情")
    operator = Column(String(100), comment="操作人")
    result = Column(String(50), comment="操作结果(success/failed)")
    error_message = Column(Text, comment="错误信息")
    created_at = Column(DateTime, default=datetime.utcnow, comment="操作时间")
    
    # 关联关系
    order = relationship("Order", back_populates="logs")


class PolicyVersion(Base):
    """策略版本表"""
    __tablename__ = "policy_versions"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True, comment="工单ID")
    version_type = Column(String(20), nullable=False, comment="版本类型: original/formatted/user_modified")
    data = Column(JSON, nullable=False, comment="策略数据(JSON格式)")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    # 关联关系
    order = relationship("Order")
