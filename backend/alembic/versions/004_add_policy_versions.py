"""Add policy versions table

Revision ID: 004_add_policy_versions
Revises: 003_fix_service_type
Create Date: 2026-03-06 10:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_add_policy_versions'
down_revision = '003_fix_service_type'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 policy_versions 表
    op.create_table(
        'policy_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('version_type', sa.String(length=20), nullable=False),
        sa.Column('data', postgresql.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_policy_versions_id'), 'policy_versions', ['id'], unique=False)
    op.create_index(op.f('ix_policy_versions_order_id'), 'policy_versions', ['order_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_policy_versions_order_id'), table_name='policy_versions')
    op.drop_index(op.f('ix_policy_versions_id'), table_name='policy_versions')
    op.drop_table('policy_versions')
