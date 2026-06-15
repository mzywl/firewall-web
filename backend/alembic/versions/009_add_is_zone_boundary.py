"""add is_zone_boundary to firewalls

Revision ID: 009_add_is_zone_boundary
Revises: b2c3d4e5f6a7
Create Date: 2026-06-15 15:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009_add_is_zone_boundary'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    """添加 is_zone_boundary 字段（是否区域边界防火墙）"""
    op.add_column('firewalls',
        sa.Column('is_zone_boundary', sa.Integer(),
                  nullable=False, server_default='0',
                  comment='是否区域边界防火墙(0:否, 1:是)；仅边界防火墙需配 NAT 地址池')
    )


def downgrade():
    """回滚：删除 is_zone_boundary 字段"""
    op.drop_column('firewalls', 'is_zone_boundary')
