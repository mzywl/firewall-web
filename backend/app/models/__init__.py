"""SQLAlchemy 数据库模型 — 严格对齐 重构.md §1 spec

"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum


# ==========================================
# 枚举类型
# ==========================================

class OrderStatus(str, enum.Enum):
    """工单状态"""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class FirewallType(str, enum.Enum):
    """防火墙厂商类型 (重构.md §1 精简后)"""
    fortigate = "fortigate"
    huawei = "huawei"
    h3c = "h3c"
    hillstone = "hillstone"
    sangfor = "sangfor"
    other = "other"


class ConnectionType(str, enum.Enum):
    """连接方式 (重构.md §1 只保留 ssh/api)"""
    ssh = "ssh"
    api = "api"


class PushMode(str, enum.Enum):
    """推送模式 (重构.md §3 三 mode 隔离)"""
    force_push = "force_push"       # 全新强制推送: 对象与策略全错开新建
    reuse_objects = "reuse_objects"  # 对象复用模式: 复用相同 IP/端口组, 策略行新建
    deduplicate = "deduplicate"     # 策略全量查重: 复用对象 + 整条策略一致则完全复用


class PushSnapshotStatus(str, enum.Enum):
    """推送快照状态"""
    running = "running"
    success = "success"
    failed = "failed"
    partial = "partial"


class PushLogLevel(str, enum.Enum):
    """推送日志级别"""
    info = "info"
    success = "success"
    warning = "warning"
    error = "error"

# ==========================================
# 1. 资产与网络矩阵模块
# ==========================================

class Firewall(Base):
    """防火墙元数据表 (重构.md §1 精简后)

    已删除字段 (历史累计, 本次清理):
      - region → belong_region (重命名, 语义不变: 防火墙所在大区)
      - covered_region (NAT 透传 key 已迁到 ZoneAccessConfig)
      - local_zone_name / external_zone_name (zone 寻路已迁到 ZoneAccessConfig.boundary_*)
      - internal_protected_ips / external_protected_ips (spec 不要)
      - supported_policy_types (已废弃)
      - outbound_snat_pool / inbound_snat_pool (NAT 池已迁到 ZoneAccessConfig.snat_pool)
      - allow_same_firewall_push (chain_planner 已绕开)
      - push_contact / push_remark / remark (UI 无引用)
    """
    __tablename__ = "firewalls"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, comment="防火墙名称")
    alias = Column(String(100), comment="别名")
    type = Column(Enum(FirewallType), nullable=False, comment="防火墙物理厂商类型")
    management_ip = Column(String(50), nullable=False, comment="管理IP")

    belong_region = Column(String(100), nullable=True, comment="所属大区(组织归属)")
    is_zone_boundary = Column(Integer, default=0, comment="是否属于跨区域边界防火墙(0:否, 1:是)")

    connection_type = Column(Enum(ConnectionType), nullable=False, default=ConnectionType.ssh)
    connection_config = Column(JSON, comment="连接凭据详情")

    auto_push = Column(Integer, default=1, comment="是否激活自动推送(0:否, 1:是)")
    status = Column(String(20), default="enabled", comment="运维状态: enabled/disabled")
    is_active = Column(Integer, default=1, comment="软删除标识")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zones = relationship("FirewallZone", back_populates="firewall", cascade="all, delete-orphan")
    zone_access_configs = relationship("ZoneAccessConfig", back_populates="firewall")


class FirewallZone(Base):
    """设备安全域与资产网段表

    已删除字段:
      - description (spec 不要)
    已新增字段:
      - connect_region (spec 要求, 表达当前安全域连接的大区)
      - zone_role (设计文档 §1 要求, 显式标记 internal/external 防护域,
                   替代旧隐式判定 connect_region == fw.belong_region)
    """
    __tablename__ = "firewall_zones"

    id = Column(Integer, primary_key=True, index=True)
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), nullable=False)
    zone_name = Column(String(100), nullable=False, comment="防火墙本地接口域名称")
    protected_ips = Column(Text, comment="该安全域技术保护的网段资产, 每行一个标准 CIDR")
    connect_region = Column(String(100), nullable=False, comment="核心映射标签: 当前安全域技术上代表/连接着的全局宏观大区域")
    zone_role = Column(
        String(20), nullable=False, server_default='internal',
        comment="设计文档 §1: 显式域角色 (internal=内部防护, external=外部防护)"
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    firewall = relationship("Firewall", back_populates="zones")


class ZoneAccessConfig(Base):
    """全局区域访问与 NAT 路径矩阵

    已重命名字段:
      - source_zone → source_region (跟 belong_region 一致用 "region" 后缀)
      - dest_zone → dest_region
    已删除字段:
      - created_by (spec 不要)
    已新增字段 (spec 要求的 4 个边界 NAT 寻路关键字段):
      - boundary_source_zone (NN): 边界墙面向源大区的本地 Zone 名称
      - boundary_dest_zone (NN): 边界墙面向目的大区的本地 Zone 名称
      - need_nat: 此路径是否强制 SNAT
      - snat_pool: 路径专属 SNAT 转换地址池
    """
    __tablename__ = "zone_access_configs"

    id = Column(Integer, primary_key=True, index=True)
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), nullable=False, comment="扼守此大区通道的边界防火墙ID")

    # 宏观多墙寻路标签
    source_region = Column(String(100), nullable=False, comment="源宏观大区名称")
    dest_region = Column(String(100), nullable=False, comment="目的宏观大区名称")

    # 边界墙直接落地 Zone (彻底根除 trust/untrust 同名造成的语义冲突)
    boundary_source_zone = Column(String(100), nullable=False, comment="当前边界墙面向源大区的本地 Zone 名称")
    boundary_dest_zone = Column(String(100), nullable=False, comment="当前边界墙面向目的大区的本地 Zone 名称")

    # NAT 控制属性
    need_nat = Column(Integer, default=0, comment="此跨区路径是否强制做源地址转换 SNAT (0:否, 1:是)")
    snat_pool = Column(String(500), nullable=True, comment="当前路径专属 SNAT 转换地址池 (如: 192.168.1.1-1.8)")

    description = Column(Text, comment="路径规划备注")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    firewall = relationship("Firewall", back_populates="zone_access_configs")


# ==========================================
# 2. 工单与动态策略下发模块
# ==========================================

class Order(Base):
    """工单主表

    已删除:
      - logs 关系 (OperationLog 表整体删除, spec 不要)
    """
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String(50), unique=True, index=True, nullable=False, comment="唯一工单编号")
    title = Column(String(200), nullable=False)
    description = Column(Text)
    excel_file_path = Column(String(500))
    status = Column(Enum(OrderStatus), default=OrderStatus.pending)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    policies = relationship("Policy", back_populates="order", cascade="all, delete-orphan")


class Policy(Base):
    """孪生策略明细表 (存储经过路径解耦与链式 IP 重写后的实际放行形态)

    已删除字段 (本次清理):
      - action (从未使用, spec 不要)
      - is_merged (PolicyMerger 已删, spec 不要)
      - merged_policy_id (同上)
      - updated_at (spec 只有 created_at)
    已规范字段:
      - firewall_id 改为 nullable=False (spec 强制)
      - source_ip / dest_ip / service 改为 nullable=False (spec 强制)
      - device_source_zone / device_dest_zone 改为 nullable=False (spec 强制)
      - push_status 默认值 "pending" (spec 要求)
      - source_snat_ip typo 修正: "=Column(" → " = Column("
    """
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), nullable=False, comment="当前策略行落地执行的物理防火墙")

    # 动态链式改写后的四元组参数
    source_ip = Column(String(500), nullable=False, comment="该墙放行的源IP (可能已被边界墙重写为 SNAT 池)")
    dest_ip = Column(String(500), nullable=False, comment="目的IP")
    service = Column(String(500), nullable=False, comment="服务端口组")
    usage_time = Column(String(255), nullable=True, comment="标准化时间策略")

    # 业务归属可追溯性
    source_system_name = Column(String(100), comment="Excel 解析得到的源系统名")
    dest_system_name = Column(String(100), comment="Excel 解析得到的目的系统名")

    # 精确寻路落地数据
    device_source_zone = Column(String(100), nullable=False, comment="系统计算出来的本地物理入向安全域")
    device_dest_zone = Column(String(100), nullable=False, comment="系统计算出来的本地物理出向安全域")
    source_snat_ip = Column(String(500), nullable=True, comment="若当前节点为边界墙且需要 SNAT, 记录下发的专属池, 否则留空")
    # 执行状态
    push_status = Column(String(50), default="pending", comment="单个物理策略放行状态 (pending/success/failed/reused)")
    push_result = Column(Text)
    pushed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="policies")
    firewall = relationship("Firewall")


class PolicyVersion(Base):
    """策略历史版本快照表

    已删除字段:
      - created_by 字段本来就没,无需动
      - index=True 从 order_id 移除 (spec 不要求)
    """
    __tablename__ = "policy_versions"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    version_type = Column(String(30), nullable=False, comment="状态分类: original(纯原始 Excel 解析数据)/formatted")
    data = Column(JSON, nullable=False, comment="全量 JSON 序列化载荷")
    created_at = Column(DateTime, default=datetime.utcnow)


# ==========================================
# 3. 推送快照、全量查重与流式日志模块
# ==========================================

class PushedPolicySnapshot(Base):
    """推送批次追溯主快照表

    已删除字段:
      - appended_policies (spec 只有 total/new/reused/failed 4 个计数)
      - created_at (spec 只有 started_at/finished_at)
    """
    __tablename__ = "pushed_policy_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    firewall_id = Column(Integer, ForeignKey("firewalls.id"), nullable=False)
    batch_id = Column(String(50), nullable=False, index=True, comment="单次下发流水的批次 UUID")

    push_mode = Column(Enum(PushMode), nullable=False, comment="前端指定的查重推送机制")
    status = Column(Enum(PushSnapshotStatus), default=PushSnapshotStatus.running)

    # 统计数据计数
    total_policies = Column(Integer, default=0)
    new_policies = Column(Integer, default=0)
    reused_policies = Column(Integer, default=0)
    failed_policies = Column(Integer, default=0)

    # 发生态冷备份快照 (文本持久化, 排除后期因人为更改设备导致审计失效)
    fetched_addresses_json = Column(Text, comment="下发前从物理防火墙上拉取的全量地址对象备份")
    fetched_services_json = Column(Text, comment="下发前从物理防火墙上拉取的全量端口对象备份")
    fetched_policies_json = Column(Text, comment="下发前从物理防火墙上拉取的全量安全策略行备份")

    error_log = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    items = relationship("PushedPolicyItem", back_populates="snapshot", cascade="all, delete-orphan")
    logs = relationship(
        "PushLog", back_populates="snapshot",
        cascade="all, delete-orphan", order_by="PushLog.seq",
    )
    order = relationship("Order")
    firewall = relationship("Firewall")


class PushedPolicyItem(Base):
    """每条策略的高精特征与回滚审计明细表

    已删除字段:
      - order_id (可通过 snapshot.order_id 推导)
      - firewall_id (可通过 snapshot.firewall_id 推导)
      - src_addr_key / dst_addr_key / service_key / schedule_key (spec 只要 match_key)
      - device_policy_name (spec 只要 device_policy_id)
      - created_at (spec 不要)
    """
    __tablename__ = "pushed_policy_items"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("pushed_policy_snapshots.id"), nullable=False)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=False)

    # 核心高精查重依据
    match_key = Column(String(64), index=True, comment="标准化处理后的 4 维度参数 SHA1 前 30 位摘要")

    # 设备真实创建/复用的命名对象线索
    device_src_obj = Column(String(200), comment="设备侧真实源地址组/对象名称")
    device_dst_obj = Column(String(200), comment="设备侧真实目的地址组/对象名称")
    device_service_obj = Column(String(200), comment="设备侧真实端口组对象名称")
    device_schedule_obj = Column(String(200), comment="设备侧真实时间对象名称")

    # 设备侧落地物理标识
    device_policy_id = Column(String(100), comment="物理设备返回的真实策略 ID 或 Rule 唯一索引名称")
    action = Column(String(20), comment="具体动作: created / reused / failed")
    raw_commands = Column(Text, comment="该设备真实执行并灌入的 CLI 命令块, 用于追溯与单线回滚")
    error_msg = Column(Text)

    snapshot = relationship("PushedPolicySnapshot", back_populates="items")
    policy = relationship("Policy")


class PushLog(Base):
    """基于单步发射机制的即时流水线日志表 (供前端高频轮询渲染)

    spec 字段无变化, 已对齐。
    """
    __tablename__ = "push_logs"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("pushed_policy_snapshots.id"), nullable=False)
    seq = Column(Integer, nullable=False, comment="单批次快照内从 1 开始的自增强保序序号")
    stage = Column(String(50), nullable=False, comment="下发阶段: connect/fetch/match/push_obj/push_rule")
    level = Column(Enum(PushLogLevel), default=PushLogLevel.info)
    message = Column(String(1000), nullable=False, comment="日志正文说明")
    data_json = Column(Text, comment="附带的细化排查底层回显 JSON 数据")
    created_at = Column(DateTime, default=datetime.utcnow)

    snapshot = relationship("PushedPolicySnapshot", back_populates="logs")