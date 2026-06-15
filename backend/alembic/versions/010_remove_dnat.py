"""remove DNAT-related fields

Revision ID: 010_remove_dnat
Revises: 009_add_is_zone_boundary
Create Date: 2026-06-15 22:30:00

项目决定: 取消 DNAT 分析。以后 NAT 分析仅按 SNAT 处理。

本迁移删除以下字段：
- firewalls.inbound_dnat_pool      入向 DNAT 地址段
- firewalls.outbound_dnat_pool     出向 DNAT 地址段
- zone_access_configs.nat_type     区域访问配置中的 NAT 类型
- zone_access_rules.nat_type       区域访问规则中的 NAT 类型

保留：
- firewalls.outbound_snat_pool     出向 SNAT 地址段（仍需）
- firewalls.inbound_snat_pool      入向 SNAT 地址段（仍需）
- 防火墙模型的 is_zone_boundary   仍控制 SNAT 池的 UI 显示
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010_remove_dnat'
down_revision = '009_add_is_zone_boundary'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """删除 DNAT 相关字段"""
    # 1) 删除 firewalls 表的 DNAT 池字段
    op.drop_column('firewalls', 'inbound_dnat_pool')
    op.drop_column('firewalls', 'outbound_dnat_pool')

    # 2) 删除 zone_access_configs 表的 nat_type 字段
    op.drop_column('zone_access_configs', 'nat_type')

    # 3) 删除 zone_access_rules 表的 nat_type 字段
    op.drop_column('zone_access_rules', 'nat_type')


def downgrade() -> None:
    """回滚：恢复 DNAT 相关字段（注意：原数据已丢失，类型与注释按 models 定义恢复）"""
    # 1) 恢复 firewalls 表的 DNAT 池字段
    op.add_column('firewalls',
        sa.Column('inbound_dnat_pool', sa.Text(), nullable=True,
                  comment='入向DNAT地址段/地址池名称')
    )
    op.add_column('firewalls',
        sa.Column('outbound_dnat_pool', sa.Text(), nullable=True,
                  comment='出向DNAT地址段/地址池名称')
    )

    # 2) 恢复 zone_access_configs 表的 nat_type 字段
    op.add_column('zone_access_configs',
        sa.Column('nat_type', sa.String(length=20), nullable=True,
                  comment='NAT类型: SNAT/DNAT/BOTH/None')
    )

    # 3) 恢复 zone_access_rules 表的 nat_type 字段
    op.add_column('zone_access_rules',
        sa.Column('nat_type', sa.String(length=20), nullable=True,
                  comment='NAT类型: SNAT/DNAT/BOTH/None')
    )
