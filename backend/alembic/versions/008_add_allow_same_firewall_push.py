"""add allow_same_firewall_push to firewalls

Revision ID: 008
Revises: 007
Create Date: 2026-03-14 14:45:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    """添加 allow_same_firewall_push 字段"""
    op.add_column('firewalls', 
        sa.Column('allow_same_firewall_push', sa.Boolean(), 
                  nullable=False, server_default='0',
                  comment='是否允许同墙推送（源目的IP都在内部IP段时）')
    )


def downgrade():
    """回滚：删除 allow_same_firewall_push 字段"""
    op.drop_column('firewalls', 'allow_same_firewall_push')
