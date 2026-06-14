"""add push snapshot tables

Revision ID: a1b2c3d4e5f6
Revises: 69f06f36e1af
Create Date: 2026-06-14 20:00:00.000000

新增 2 张表：
- pushed_policy_snapshots: 每次推送的批次级快照（可追溯）
- pushed_policy_items: 每条策略的推送明细（用于查重）
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '69f06f36e1af'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 推送批次快照
    op.create_table(
        'pushed_policy_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False, comment='工单ID'),
        sa.Column('firewall_id', sa.Integer(), nullable=False, comment='防火墙ID'),
        sa.Column('batch_id', sa.String(length=50), nullable=False, comment='推送批次UUID'),
        sa.Column('push_mode', sa.String(length=20), nullable=False, comment='推送模式: deduplicate/force_push'),
        sa.Column('status', sa.String(length=20), nullable=True, comment='状态: running/success/failed'),
        sa.Column('total_policies', sa.Integer(), nullable=True, comment='工单总策略数'),
        sa.Column('new_policies', sa.Integer(), nullable=True, comment='新建数'),
        sa.Column('reused_policies', sa.Integer(), nullable=True, comment='复用整条数（仅deduplicate模式）'),
        sa.Column('appended_policies', sa.Integer(), nullable=True, comment='追加数（仅deduplicate模式）'),
        sa.Column('failed_policies', sa.Integer(), nullable=True, comment='失败数'),
        # 拉取的设备侧快照（用于可追溯 + 后续查重）
        sa.Column('fetched_addresses_json', sa.Text(), nullable=True, comment='拉取的地址对象JSON'),
        sa.Column('fetched_policies_json', sa.Text(), nullable=True, comment='拉取的策略JSON'),
        sa.Column('fetched_services_json', sa.Text(), nullable=True, comment='拉取的端口对象JSON'),
        # 错误日志
        sa.Column('error_log', sa.Text(), nullable=True, comment='错误日志'),
        # 时间
        sa.Column('started_at', sa.DateTime(), nullable=True, comment='开始时间'),
        sa.Column('finished_at', sa.DateTime(), nullable=True, comment='结束时间'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['firewall_id'], ['firewalls.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pushed_policy_snapshots_id'), 'pushed_policy_snapshots', ['id'], unique=False)
    op.create_index(op.f('ix_pushed_policy_snapshots_batch_id'), 'pushed_policy_snapshots', ['batch_id'], unique=False)
    op.create_index(op.f('ix_pushed_policy_snapshots_order_id'), 'pushed_policy_snapshots', ['order_id'], unique=False)
    op.create_index(op.f('ix_pushed_policy_snapshots_firewall_id'), 'pushed_policy_snapshots', ['firewall_id'], unique=False)

    # 2) 每条策略推送明细（用于精确查重 + 可追溯）
    op.create_table(
        'pushed_policy_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False, comment='所属快照ID'),
        sa.Column('order_id', sa.Integer(), nullable=False, comment='工单ID'),
        sa.Column('firewall_id', sa.Integer(), nullable=False, comment='防火墙ID'),
        sa.Column('policy_id', sa.Integer(), nullable=True, comment='工单中的Policy表ID'),
        # 4 维度匹配键（用于查重）
        sa.Column('match_key', sa.String(length=64), nullable=True, comment='4维度的hash，用于快速查重'),
        sa.Column('src_addr_key', sa.String(length=2000), nullable=True, comment='源IP（排序去重后）'),
        sa.Column('dst_addr_key', sa.String(length=2000), nullable=True, comment='目的IP（排序去重后）'),
        sa.Column('service_key', sa.String(length=500), nullable=True, comment='端口（排序去重后）'),
        sa.Column('schedule_key', sa.String(length=100), nullable=True, comment='有效期（标准化）'),
        # 设备上实际的对象名
        sa.Column('device_src_obj', sa.String(length=200), nullable=True, comment='设备上源地址对象名'),
        sa.Column('device_dst_obj', sa.String(length=200), nullable=True, comment='设备上目的地址对象名'),
        sa.Column('device_service_obj', sa.String(length=200), nullable=True, comment='设备上端口对象名'),
        sa.Column('device_schedule_obj', sa.String(length=200), nullable=True, comment='设备上时间对象名'),
        # 设备上的策略标识
        sa.Column('device_policy_id', sa.String(length=100), nullable=True, comment='设备上的策略ID/H3C rule name等'),
        sa.Column('device_policy_name', sa.String(length=200), nullable=True, comment='设备上的策略名'),
        # 动作
        sa.Column('action', sa.String(length=20), nullable=True, comment='动作: created/reused/appended/failed'),
        sa.Column('raw_commands', sa.Text(), nullable=True, comment='实际推送的命令（用于回滚/审计）'),
        sa.Column('error_msg', sa.Text(), nullable=True, comment='本条的错误信息'),
        # 时间
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['snapshot_id'], ['pushed_policy_snapshots.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['firewall_id'], ['firewalls.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pushed_policy_items_id'), 'pushed_policy_items', ['id'], unique=False)
    op.create_index(op.f('ix_pushed_policy_items_snapshot_id'), 'pushed_policy_items', ['snapshot_id'], unique=False)
    op.create_index(op.f('ix_pushed_policy_items_match_key'), 'pushed_policy_items', ['match_key'], unique=False)
    op.create_index(op.f('ix_pushed_policy_items_firewall_id'), 'pushed_policy_items', ['firewall_id'], unique=False)
    # 复合索引：常用查重查询 (firewall_id + match_key)
    op.create_index('ix_pushed_items_fw_matchkey', 'pushed_policy_items', ['firewall_id', 'match_key'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_pushed_items_fw_matchkey', table_name='pushed_policy_items')
    op.drop_index(op.f('ix_pushed_policy_items_firewall_id'), table_name='pushed_policy_items')
    op.drop_index(op.f('ix_pushed_policy_items_match_key'), table_name='pushed_policy_items')
    op.drop_index(op.f('ix_pushed_policy_items_snapshot_id'), table_name='pushed_policy_items')
    op.drop_index(op.f('ix_pushed_policy_items_id'), table_name='pushed_policy_items')
    op.drop_table('pushed_policy_items')

    op.drop_index(op.f('ix_pushed_policy_snapshots_firewall_id'), table_name='pushed_policy_snapshots')
    op.drop_index(op.f('ix_pushed_policy_snapshots_order_id'), table_name='pushed_policy_snapshots')
    op.drop_index(op.f('ix_pushed_policy_snapshots_batch_id'), table_name='pushed_policy_snapshots')
    op.drop_index(op.f('ix_pushed_policy_snapshots_id'), table_name='pushed_policy_snapshots')
    op.drop_table('pushed_policy_snapshots')
