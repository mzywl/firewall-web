"""Initial migration

Revision ID: 001_initial
Revises: 
Create Date: 2026-03-05 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 orders 表
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_no', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('excel_file_path', sa.String(length=500), nullable=True),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', name='orderstatus'), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_id'), 'orders', ['id'], unique=False)
    op.create_index(op.f('ix_orders_order_no'), 'orders', ['order_no'], unique=True)

    # 创建 firewalls 表
    op.create_table(
        'firewalls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.Enum('fortigate', 'hillstone', 'leadsec', 'h3c', name='firewalltype'), nullable=False),
        sa.Column('host', sa.String(length=100), nullable=False),
        sa.Column('port', sa.Integer(), nullable=True),
        sa.Column('username', sa.String(length=100), nullable=True),
        sa.Column('password', sa.String(length=200), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_firewalls_id'), 'firewalls', ['id'], unique=False)

    # 创建 policies 表
    op.create_table(
        'policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('firewall_id', sa.Integer(), nullable=True),
        sa.Column('source_zone', sa.String(length=100), nullable=True),
        sa.Column('dest_zone', sa.String(length=100), nullable=True),
        sa.Column('source_ip', sa.String(length=500), nullable=True),
        sa.Column('dest_ip', sa.String(length=500), nullable=True),
        sa.Column('service', sa.String(length=500), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=True),
        sa.Column('is_merged', sa.Integer(), nullable=True),
        sa.Column('merged_policy_id', sa.Integer(), nullable=True),
        sa.Column('push_status', sa.String(length=50), nullable=True),
        sa.Column('push_result', sa.Text(), nullable=True),
        sa.Column('pushed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['firewall_id'], ['firewalls.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_policies_id'), 'policies', ['id'], unique=False)

    # 创建 operation_logs 表
    op.create_table(
        'operation_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('operation_type', sa.String(length=50), nullable=False),
        sa.Column('operation_detail', sa.Text(), nullable=True),
        sa.Column('operator', sa.String(length=100), nullable=True),
        sa.Column('result', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_operation_logs_id'), 'operation_logs', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_operation_logs_id'), table_name='operation_logs')
    op.drop_table('operation_logs')
    op.drop_index(op.f('ix_policies_id'), table_name='policies')
    op.drop_table('policies')
    op.drop_index(op.f('ix_firewalls_id'), table_name='firewalls')
    op.drop_table('firewalls')
    op.drop_index(op.f('ix_orders_order_no'), table_name='orders')
    op.drop_index(op.f('ix_orders_id'), table_name='orders')
    op.drop_table('orders')
