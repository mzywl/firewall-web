from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum


class OrderStatus(str, enum.Enum):
    """工单状态"""
    pending = "pending"  # 待处理
    processing = "processing"  # 处理中
    completed = "completed"  # 已完成
    failed = "failed"  # 失败


class FirewallType(str, enum.Enum):
    """防火墙类型"""
    fortigate = "fortigate"
    hillstone = "hillstone"
    leadsec = "leadsec"
    h3c = "h3c"
    guanqun = "guanqun"  # 冠群
    feita = "feita"  # 飞塔
    wangshen = "wangshen"  # 网神
    sangfor = "sangfor"  # 深信服
    huawei = "huawei"  # 华为
    shanshi = "shanshi"  # 山石
    other = "other"  # 其他


class ConnectionType(str, enum.Enum):
    """连接方式"""
    ssh = "ssh"
    api = "api"
    cli = "cli"
    manual = "manual"


class Order(Base):
    """工单表"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String(50), unique=True, index=True, nullable=False, comment="工单编号")
    title = Column(String(200), nullable=False, comment="工单标题")
    description = Column(Text, comment="工单描述")
    excel_file_path = Column(String(500), comment="Excel文件路径")
    status = Column(Enum(OrderStatus), default=OrderStatus.pending, comment="工单状态")
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
    
    # 基础信息
    name = Column(String(200), nullable=False, comment="防火墙名称")
    alias = Column(String(100), comment="简称/别名")
    type = Column(Enum(FirewallType), nullable=False, comment="防火墙类型")
    management_ip = Column(String(50), nullable=False, comment="管理IP")
    
    # 区域信息
    region = Column(String(100), comment="所属区域")
    local_zone_name = Column(String(100), comment="本地防护区域名称")
    external_zone_name = Column(String(100), comment="外部防护区域名称")
    
    # 连接方式
    connection_type = Column(Enum(ConnectionType), nullable=False, default=ConnectionType.ssh, comment="连接类型")
    connection_config = Column(JSON, comment="连接配置(根据type存不同结构)")
    
    # 防护范围（分内部和外部）
    internal_protected_ips = Column(Text, comment="内部防护IP段，每行一个")
    external_protected_ips = Column(Text, comment="外部防护IP段，每行一个")
    supported_policy_types = Column(JSON, comment="支持的策略类型数组")
    
    # NAT配置
    outbound_snat_pool = Column(Text, comment="出向SNAT地址段/地址池名称")
    inbound_dnat_pool = Column(Text, comment="入向DNAT地址段/地址池名称")
    inbound_snat_pool = Column(Text, comment="入向SNAT地址段/地址池名称")
    outbound_dnat_pool = Column(Text, comment="出向DNAT地址段/地址池名称")
    
    # 推送配置
    auto_push = Column(Integer, default=1, comment="是否支持自动推送(0:否, 1:是)")
    allow_same_firewall_push = Column(Integer, default=0, comment="是否允许同墙推送（源目的IP都在内部IP段时）(0:否, 1:是)")
    push_contact = Column(String(100), comment="推送责任人")
    push_remark = Column(Text, comment="推送备注")
    
    # 状态和备注
    status = Column(String(20), default="enabled", comment="状态(enabled/disabled)")
    remark = Column(Text, comment="备注")
    
    is_active = Column(Integer, default=1, comment="是否启用(0:否, 1:是)")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    zones = relationship("FirewallZone", back_populates="firewall", cascade="all, delete-orphan")


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


class ZoneAccessConfig(Base):
    """区域访问配置表"""
    __tablename__ = "zone_access_configs"

    id = Column(Integer, primary_key=True, index=True)
    source_zone = Column(String(100), nullable=False, comment="源区域")
    dest_zone = Column(String(100), nullable=False, comment="目的区域")
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), nullable=False, comment="防火墙ID")
    nat_type = Column(String(20), comment="NAT类型: SNAT/DNAT/BOTH/None")
    description = Column(Text, comment="配置说明")
    created_by = Column(String(100), comment="创建人")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    firewall = relationship("Firewall")


class FirewallZone(Base):
    """防火墙区域表"""
    __tablename__ = "firewall_zones"

    id = Column(Integer, primary_key=True, index=True)
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), nullable=False, comment="防火墙ID")
    zone_name = Column(String(100), nullable=False, comment="区域名称")
    protected_ips = Column(Text, comment="保护的IP段（每行一个网段）")
    description = Column(Text, comment="区域描述")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    firewall = relationship("Firewall", back_populates="zones")


class ZoneAccessRule(Base):
    """区域访问规则表"""
    __tablename__ = "zone_access_rules"

    id = Column(Integer, primary_key=True, index=True)
    source_zone_id = Column(Integer, ForeignKey("firewall_zones.id"), nullable=False, comment="源区域ID")
    dest_zone_id = Column(Integer, ForeignKey("firewall_zones.id"), nullable=False, comment="目的区域ID")
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), nullable=False, comment="防火墙ID")
    allow_access = Column(Integer, default=1, comment="是否允许访问（1=允许，0=拒绝）")
    nat_type = Column(String(20), comment="NAT类型: SNAT/DNAT/BOTH/None")
    description = Column(Text, comment="规则描述")
    created_by = Column(String(100), comment="创建人")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    source_zone = relationship("FirewallZone", foreign_keys=[source_zone_id])
    dest_zone = relationship("FirewallZone", foreign_keys=[dest_zone_id])
    firewall = relationship("Firewall")
