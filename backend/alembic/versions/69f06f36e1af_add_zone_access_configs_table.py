"""add zone_access_configs table

Revision ID: 69f06f36e1af
Revises: 008_add_allow_same_firewall_push
Create Date: 2026-03-16 19:49:43.345151

精简版（原版是 alembic auto-generated 的 529 行，有大量重复的 alter_column 加注释
和 create_index 操作，跑到已存在的 DB 上会冲突。本版只保留真正新增的 schema 内容）：
1. 新建 zone_access_configs 表
2. 把 firewalls.allow_same_firewall_push 从 Boolean 改成 Integer（与模型一致）
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '69f06f36e1af'
down_revision = '008_add_allow_same_firewall_push'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 新建 zone_access_configs 表（独立配置，存字符串形式的 zone 名字）
    op.create_table(
        'zone_access_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_zone', sa.String(length=100), nullable=False, comment='源区域'),
        sa.Column('dest_zone', sa.String(length=100), nullable=False, comment='目的区域'),
        sa.Column('firewall_id', sa.Integer(), nullable=False, comment='防火墙ID'),
        sa.Column('nat_type', sa.String(length=20), nullable=True, comment='NAT类型: SNAT/DNAT/BOTH/None'),
        sa.Column('description', sa.Text(), nullable=True, comment='配置说明'),
        sa.Column('created_by', sa.String(length=100), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
        sa.ForeignKeyConstraint(['firewall_id'], ['firewalls.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_zone_access_configs_id'),
        'zone_access_configs',
        ['id'],
        unique=False,
    )

    # 2) 新建 firewall_zones 表（显式声明"某台防火墙有哪个 zone"）
    op.create_table(
        'firewall_zones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('firewall_id', sa.Integer(), nullable=False, comment='防火墙ID'),
        sa.Column('zone_name', sa.String(length=100), nullable=False, comment='区域名称'),
        sa.Column('protected_ips', sa.Text(), nullable=True, comment='保护的IP段（每行一个网段）'),
        sa.Column('description', sa.Text(), nullable=True, comment='区域描述'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
        sa.ForeignKeyConstraint(['firewall_id'], ['firewalls.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_firewall_zones_id'),
        'firewall_zones',
        ['id'],
        unique=False,
    )

    # 3) 新建 zone_access_rules 表（基于 firewall_zones.id 的精细规则）
    op.create_table(
        'zone_access_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_zone_id', sa.Integer(), nullable=False, comment='源区域ID'),
        sa.Column('dest_zone_id', sa.Integer(), nullable=False, comment='目的区域ID'),
        sa.Column('firewall_id', sa.Integer(), nullable=False, comment='防火墙ID'),
        sa.Column('allow_access', sa.Integer(), nullable=True, comment='是否允许访问（1=允许，0=拒绝）'),
        sa.Column('nat_type', sa.String(length=20), nullable=True, comment='NAT类型: SNAT/DNAT/BOTH/None'),
        sa.Column('description', sa.Text(), nullable=True, comment='规则描述'),
        sa.Column('created_by', sa.String(length=100), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
        sa.ForeignKeyConstraint(['firewall_id'], ['firewalls.id'], ),
        sa.ForeignKeyConstraint(['source_zone_id'], ['firewall_zones.id'], ),
        sa.ForeignKeyConstraint(['dest_zone_id'], ['firewall_zones.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_zone_access_rules_id'),
        'zone_access_rules',
        ['id'],
        unique=False,
    )

    # 4) 把 allow_same_firewall_push 从 Boolean 改成 Integer
    #    PG 不能自动把 boolean default 转 integer default，必须分三步：
    op.execute("ALTER TABLE firewalls ALTER COLUMN allow_same_firewall_push DROP DEFAULT")
    op.execute(
        "ALTER TABLE firewalls ALTER COLUMN allow_same_firewall_push "
        "TYPE INTEGER USING allow_same_firewall_push::integer"
    )
    op.execute("ALTER TABLE firewalls ALTER COLUMN allow_same_firewall_push SET DEFAULT 0")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE firewalls ALTER COLUMN allow_same_firewall_push "
        "TYPE BOOLEAN USING allow_same_firewall_push::boolean"
    )
    op.execute("ALTER TABLE firewalls ALTER COLUMN allow_same_firewall_push SET DEFAULT false")
    op.drop_index(op.f('ix_zone_access_rules_id'), table_name='zone_access_rules')
    op.drop_table('zone_access_rules')
    op.drop_index(op.f('ix_firewall_zones_id'), table_name='firewall_zones')
    op.drop_table('firewall_zones')
    op.drop_index(op.f('ix_zone_access_configs_id'), table_name='zone_access_configs')
    op.drop_table('zone_access_configs')
