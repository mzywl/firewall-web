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



class PushMode(str, enum.Enum):
    """推送模式"""
    deduplicate = "deduplicate"  # 查重模式：复用整条 + 复用对象
    force_push = "force_push"    # 全推模式：只复用对象，整条必新建


class PushSnapshotStatus(str, enum.Enum):
    """推送快照状态"""
    running = "running"
    success = "success"
    failed = "failed"
    partial = "partial"  # 部分成功


class PushedPolicySnapshot(Base):
    """已推送策略批次快照（可追溯 + 查重用）"""
    __tablename__ = "pushed_policy_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True, comment="工单ID")
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), nullable=False, index=True, comment="防火墙ID")
    batch_id = Column(String(50), nullable=False, index=True, comment="推送批次UUID")

    push_mode = Column(Enum(PushMode), nullable=False, comment="推送模式")
    status = Column(Enum(PushSnapshotStatus), default=PushSnapshotStatus.running, comment="状态")

    # 统计
    total_policies = Column(Integer, default=0, comment="工单总策略数")
    new_policies = Column(Integer, default=0, comment="新建数")
    reused_policies = Column(Integer, default=0, comment="复用整条数（仅deduplicate模式）")
    appended_policies = Column(Integer, default=0, comment="追加数（仅deduplicate模式）")
    failed_policies = Column(Integer, default=0, comment="失败数")

    # 设备侧拉取的快照（全量存，可追溯）
    fetched_addresses_json = Column(Text, comment="拉取的地址对象JSON")
    fetched_policies_json = Column(Text, comment="拉取的策略JSON")
    fetched_services_json = Column(Text, comment="拉取的端口对象JSON")

    # 错误
    error_log = Column(Text, comment="错误日志")

    # 时间
    started_at = Column(DateTime, default=datetime.utcnow, comment="开始时间")
    finished_at = Column(DateTime, comment="结束时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关联
    items = relationship("PushedPolicyItem", back_populates="snapshot", cascade="all, delete-orphan")
    order = relationship("Order")
    firewall = relationship("Firewall")


class PushedPolicyItem(Base):
    """每条策略的推送明细（用于精确查重 + 回滚/审计）"""
    __tablename__ = "pushed_policy_items"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("pushed_policy_snapshots.id"), nullable=False, index=True, comment="所属快照ID")
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, comment="工单ID")
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), nullable=False, index=True, comment="防火墙ID")
    policy_id = Column(Integer, comment="工单中的Policy表ID")

    # 4 维度匹配键（用于查重）
    match_key = Column(String(64), index=True, comment="4维度hash（SHA1前30位）")
    src_addr_key = Column(String(2000), comment="源IP（排序去重）")
    dst_addr_key = Column(String(2000), comment="目的IP（排序去重）")
    service_key = Column(String(500), comment="端口（排序去重）")
    schedule_key = Column(String(100), comment="有效期（标准化）")

    # 设备上实际对象名
    device_src_obj = Column(String(200), comment="设备上源地址对象名")
    device_dst_obj = Column(String(200), comment="设备上目的地址对象名")
    device_service_obj = Column(String(200), comment="设备上端口对象名")
    device_schedule_obj = Column(String(200), comment="设备上时间对象名")

    # 设备上的策略标识
    device_policy_id = Column(String(100), comment="设备上策略ID/H3C rule name等")
    device_policy_name = Column(String(200), comment="设备上策略名")

    # 动作
    action = Column(String(20), comment="created/reused/appended/failed")
    raw_commands = Column(Text, comment="实际推送的命令（用于回滚/审计）")
    error_msg = Column(Text, comment="本条错误信息")

    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关联
    snapshot = relationship("PushedPolicySnapshot", back_populates="items")


class PushLogLevel(str, enum.Enum):
    """推送日志级别"""
    info = "info"
    success = "success"
    warning = "warning"
    error = "error"


class PushLog(Base):
    """推送实时日志（流水线每一步 emit 一行）

    用途：前端轮询拿，~1.5s 延迟即可视；持久化到 DB 便于故障排查。
    """
    __tablename__ = "push_logs"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("pushed_policy_snapshots.id"), nullable=False, index=True, comment="所属快照ID")
    seq = Column(Integer, nullable=False, comment="递增序号（同 snapshot 内从 1 开始）")
    stage = Column(String(50), nullable=False, comment="阶段: start/load/connect/snapshot/fetch/parse/match/..."  )
    level = Column(Enum(PushLogLevel), default=PushLogLevel.info, comment="日志级别")
    message = Column(String(1000), nullable=False, comment="日志消息")
    data_json = Column(Text, comment="附加数据 JSON")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关联
    snapshot = relationship("PushedPolicySnapshot", back_populates="logs")


# 给 snapshot 加 logs 关系
PushedPolicySnapshot.logs = relationship(
    "PushLog", back_populates="snapshot",
    cascade="all, delete-orphan", order_by="PushLog.seq",
)
