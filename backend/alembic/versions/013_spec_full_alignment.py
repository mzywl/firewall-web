"""FULL 重构.md §1 spec 对齐 migration

对齐 重构.md §1 spec 完整字段集合,合并删除/重命名/新增/约束变更:

**Firewall 表:**
- DROP: covered_region, local_zone_name, external_zone_name, internal_protected_ips,
        external_protected_ips, supported_policy_types, outbound_snat_pool,
        inbound_snat_pool, allow_same_firewall_push, push_contact, push_remark, remark
- RENAME: region → belong_region

**FirewallZone 表:**
- DROP: description
- ADD: connect_region (NN, backfill from Firewall.belong_region)

**ZoneAccessConfig 表:**
- RENAME: source_zone → source_region, dest_zone → dest_region
- DROP: created_by
- ADD: boundary_source_zone (NN), boundary_dest_zone (NN), need_nat, snat_pool

**Policy 表:**
- DROP: action, is_merged, merged_policy_id, updated_at
- ALTER NN: firewall_id, source_ip, dest_ip, service, device_source_zone, device_dest_zone
- ALTER DEFAULT: push_status = 'pending'

**PushedPolicySnapshot 表:**
- DROP: appended_policies, created_at

**PushedPolicyItem 表:**
- DROP: order_id, firewall_id, src_addr_key, dst_addr_key, service_key, schedule_key,
        device_policy_name, created_at

**PG Enum:**
- pushmode: ADD VALUE 'reuse_objects'

**整表 DROP (spec 不要):**
- operation_logs
- zone_access_rules

Revision ID: 013_spec_full_alignment
Revises: 012_add_covered_region
Create Date: 2026-06-22 00:00:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013_spec_full_alignment'
down_revision = '012_add_covered_region'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """对齐 重构.md §1 spec 的完整字段变更"""

    # ==========================================
    # PG Enum: pushmode 加 'reuse_objects' 值
    # ==========================================
    # 注意: PG ALTER TYPE ADD VALUE 不能在事务块中, 用 IF NOT EXISTS 避免重复
    op.execute("ALTER TYPE pushmode ADD VALUE IF NOT EXISTS 'reuse_objects'")

    # ==========================================
    # Firewall 表
    # ==========================================
    # 1) 重命名 region → belong_region
    op.alter_column('firewalls', 'region', new_column_name='belong_region')

    # 2) DROP 12 个 spec 不要的字段
    op.drop_column('firewalls', 'covered_region')
    op.drop_column('firewalls', 'local_zone_name')
    op.drop_column('firewalls', 'external_zone_name')
    op.drop_column('firewalls', 'internal_protected_ips')
    op.drop_column('firewalls', 'external_protected_ips')
    op.drop_column('firewalls', 'supported_policy_types')
    op.drop_column('firewalls', 'outbound_snat_pool')
    op.drop_column('firewalls', 'inbound_snat_pool')
    op.drop_column('firewalls', 'allow_same_firewall_push')
    op.drop_column('firewalls', 'push_contact')
    op.drop_column('firewalls', 'push_remark')
    op.drop_column('firewalls', 'remark')

    # ==========================================
    # FirewallZone 表
    # ==========================================
    # 1) 加 connect_region (NN, backfill from belong_region)
    # backfill: 用 firewall.belong_region 兜底 (旧 zone 没法推断)
    op.execute("""
        ALTER TABLE firewall_zones
        ADD COLUMN connect_region VARCHAR(100)
    """)
    op.execute("""
        UPDATE firewall_zones z
        SET connect_region = COALESCE(f.belong_region, 'unknown')
        FROM firewalls f
        WHERE z.firewall_id = f.id AND z.connect_region IS NULL
    """)
    op.execute("""
        UPDATE firewall_zones
        SET connect_region = 'unknown'
        WHERE connect_region IS NULL
    """)
    op.alter_column('firewall_zones', 'connect_region', nullable=False)

    # 2) DROP description
    op.drop_column('firewall_zones', 'description')

    # ==========================================
    # ZoneAccessConfig 表
    # ==========================================
    # 1) 重命名 source_zone → source_region
    op.alter_column('zone_access_configs', 'source_zone', new_column_name='source_region')
    # 2) 重命名 dest_zone → dest_region
    op.alter_column('zone_access_configs', 'dest_zone', new_column_name='dest_region')

    # 3) DROP created_by
    op.drop_column('zone_access_configs', 'created_by')

    # 4) ADD boundary_source_zone (NN) + backfill
    op.execute("""
        ALTER TABLE zone_access_configs
        ADD COLUMN boundary_source_zone VARCHAR(100)
    """)
    op.execute("""
        UPDATE zone_access_configs
        SET boundary_source_zone = COALESCE(source_region, 'unknown')
        WHERE boundary_source_zone IS NULL
    """)
    op.execute("""
        UPDATE zone_access_configs
        SET boundary_source_zone = 'unknown'
        WHERE boundary_source_zone IS NULL
    """)
    op.alter_column('zone_access_configs', 'boundary_source_zone', nullable=False)

    # 5) ADD boundary_dest_zone (NN) + backfill
    op.execute("""
        ALTER TABLE zone_access_configs
        ADD COLUMN boundary_dest_zone VARCHAR(100)
    """)
    op.execute("""
        UPDATE zone_access_configs
        SET boundary_dest_zone = COALESCE(dest_region, 'unknown')
        WHERE boundary_dest_zone IS NULL
    """)
    op.execute("""
        UPDATE zone_access_configs
        SET boundary_dest_zone = 'unknown'
        WHERE boundary_dest_zone IS NULL
    """)
    op.alter_column('zone_access_configs', 'boundary_dest_zone', nullable=False)

    # 6) ADD need_nat + snat_pool
    op.add_column(
        'zone_access_configs',
        sa.Column('need_nat', sa.Integer(), nullable=True, server_default='0',
                  comment='此跨区路径是否强制 SNAT (0:否, 1:是)'),
    )
    op.add_column(
        'zone_access_configs',
        sa.Column('snat_pool', sa.String(500), nullable=True,
                  comment='路径专属 SNAT 转换地址池'),
    )

    # ==========================================
    # Policy 表
    # ==========================================
    # 1) DROP 4 个 spec 不要的字段
    op.drop_column('policies', 'action')
    op.drop_column('policies', 'is_merged')
    op.drop_column('policies', 'merged_policy_id')
    op.drop_column('policies', 'updated_at')

    # 2) 修 source_snat_ip typo (如有, 实际 schema 一致, 不需要重命名)

    # 3) ALTER NN: firewall_id (spec 强制)
    # backfill: 现有 firewall_id NULL 的设为 0 (后续手工修复; 真数据不会有 NULL)
    op.execute("UPDATE policies SET firewall_id = 0 WHERE firewall_id IS NULL")
    op.alter_column('policies', 'firewall_id', nullable=False)

    # 4) ALTER NN: source_ip / dest_ip / service (spec 强制)
    op.execute("UPDATE policies SET source_ip = '0.0.0.0/0' WHERE source_ip IS NULL OR source_ip = ''")
    op.execute("UPDATE policies SET dest_ip = '0.0.0.0/0' WHERE dest_ip IS NULL OR dest_ip = ''")
    op.execute("UPDATE policies SET service = 'any' WHERE service IS NULL OR service = ''")
    op.alter_column('policies', 'source_ip', nullable=False)
    op.alter_column('policies', 'dest_ip', nullable=False)
    op.alter_column('policies', 'service', nullable=False)

    # 5) ALTER NN: device_source_zone / device_dest_zone
    op.execute("UPDATE policies SET device_source_zone = 'any' WHERE device_source_zone IS NULL OR device_source_zone = ''")
    op.execute("UPDATE policies SET device_dest_zone = 'any' WHERE device_dest_zone IS NULL OR device_dest_zone = ''")
    op.alter_column('policies', 'device_source_zone', nullable=False)
    op.alter_column('policies', 'device_dest_zone', nullable=False)

    # 6) push_status 加 DEFAULT 'pending'
    op.execute("UPDATE policies SET push_status = 'pending' WHERE push_status IS NULL")
    op.alter_column('policies', 'push_status', server_default='pending')

    # ==========================================
    # PushedPolicySnapshot 表
    # ==========================================
    op.drop_column('pushed_policy_snapshots', 'appended_policies')
    op.drop_column('pushed_policy_snapshots', 'created_at')

    # ==========================================
    # PushedPolicyItem 表
    # ==========================================
    op.drop_column('pushed_policy_items', 'order_id')
    op.drop_column('pushed_policy_items', 'firewall_id')
    op.drop_column('pushed_policy_items', 'src_addr_key')
    op.drop_column('pushed_policy_items', 'dst_addr_key')
    op.drop_column('pushed_policy_items', 'service_key')
    op.drop_column('pushed_policy_items', 'schedule_key')
    op.drop_column('pushed_policy_items', 'device_policy_name')
    op.drop_column('pushed_policy_items', 'created_at')

    # ==========================================
    # 整表 DROP (spec 不要)
    # ==========================================
    # OperationLog 表 — 通过 cascade 删除 operation_logs (无外键引用了)
    op.drop_table('operation_logs')

    # ZoneAccessRule 表 — 通过 cascade 删除 zone_access_rules
    op.drop_table('zone_access_rules')


def downgrade() -> None:
    """回滚 — 重建旧字段 (数据已丢, 仅恢复结构)

    注意: 回滚只恢复表结构, 不能恢复已 DROP 的数据。
    """
    # 整表恢复 (空表)
    op.create_table(
        'zone_access_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_zone_id', sa.Integer()),
        sa.Column('dest_zone_id', sa.Integer()),
        sa.Column('firewall_id', sa.Integer()),
        sa.Column('allow_access', sa.Integer(), server_default='1'),
        sa.Column('description', sa.Text()),
        sa.Column('created_by', sa.String(100)),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table(
        'operation_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer()),
        sa.Column('operation_type', sa.String(50), nullable=False),
        sa.Column('operation_detail', sa.Text()),
        sa.Column('operator', sa.String(100)),
        sa.Column('result', sa.String(50)),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    # PushedPolicyItem 字段恢复
    op.add_column('pushed_policy_items', sa.Column('order_id', sa.Integer()))
    op.add_column('pushed_policy_items', sa.Column('firewall_id', sa.Integer()))
    op.add_column('pushed_policy_items', sa.Column('src_addr_key', sa.String(2000)))
    op.add_column('pushed_policy_items', sa.Column('dst_addr_key', sa.String(2000)))
    op.add_column('pushed_policy_items', sa.Column('service_key', sa.String(500)))
    op.add_column('pushed_policy_items', sa.Column('schedule_key', sa.String(100)))
    op.add_column('pushed_policy_items', sa.Column('device_policy_name', sa.String(200)))
    op.add_column('pushed_policy_items', sa.Column('created_at', sa.DateTime()))

    # PushedPolicySnapshot 字段恢复
    op.add_column('pushed_policy_snapshots', sa.Column('appended_policies', sa.Integer(), server_default='0'))
    op.add_column('pushed_policy_snapshots', sa.Column('created_at', sa.DateTime()))

    # Policy 字段恢复
    op.add_column('policies', sa.Column('action', sa.String(50)))
    op.add_column('policies', sa.Column('is_merged', sa.Integer(), server_default='0'))
    op.add_column('policies', sa.Column('merged_policy_id', sa.Integer()))
    op.add_column('policies', sa.Column('updated_at', sa.DateTime()))

    # ZoneAccessConfig 字段回滚
    op.drop_column('zone_access_configs', 'snat_pool')
    op.drop_column('zone_access_configs', 'need_nat')
    op.drop_column('zone_access_configs', 'boundary_dest_zone')
    op.drop_column('zone_access_configs', 'boundary_source_zone')
    op.add_column('zone_access_configs', sa.Column('created_by', sa.String(100)))
    op.alter_column('zone_access_configs', 'dest_region', new_column_name='dest_zone')
    op.alter_column('zone_access_configs', 'source_region', new_column_name='source_zone')

    # FirewallZone 字段回滚
    op.add_column('firewall_zones', sa.Column('description', sa.Text()))
    op.drop_column('firewall_zones', 'connect_region')

    # Firewall 字段恢复
    op.add_column('firewalls', sa.Column('remark', sa.Text()))
    op.add_column('firewalls', sa.Column('push_remark', sa.Text()))
    op.add_column('firewalls', sa.Column('push_contact', sa.String(100)))
    op.add_column('firewalls', sa.Column('allow_same_firewall_push', sa.Integer(), server_default='0'))
    op.add_column('firewalls', sa.Column('inbound_snat_pool', sa.Text()))
    op.add_column('firewalls', sa.Column('outbound_snat_pool', sa.Text()))
    op.add_column('firewalls', sa.Column('supported_policy_types', sa.JSON()))
    op.add_column('firewalls', sa.Column('external_protected_ips', sa.Text()))
    op.add_column('firewalls', sa.Column('internal_protected_ips', sa.Text()))
    op.add_column('firewalls', sa.Column('external_zone_name', sa.String(100)))
    op.add_column('firewalls', sa.Column('local_zone_name', sa.String(100)))
    op.add_column('firewalls', sa.Column('covered_region', sa.String(100)))
    op.alter_column('firewalls', 'belong_region', new_column_name='region')

    # PG enum value 'reuse_objects' 不能直接 DROP, 留待人工清理