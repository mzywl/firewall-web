"""add push_logs table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15 09:00:00.000000

新增 1 张表：
- push_logs: 推送实时日志（流水线每步 emit 一行，前端轮询拿）
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'push_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False, comment='所属快照ID'),
        sa.Column('seq', sa.Integer(), nullable=False, comment='递增序号'),
        sa.Column('stage', sa.String(length=50), nullable=False, comment='阶段'),
        sa.Column('level', sa.String(length=20), nullable=True, comment='级别: info/success/warning/error'),
        sa.Column('message', sa.String(length=1000), nullable=False, comment='日志消息'),
        sa.Column('data_json', sa.Text(), nullable=True, comment='附加数据 JSON'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['snapshot_id'], ['pushed_policy_snapshots.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_push_logs_id'), 'push_logs', ['id'], unique=False)
    op.create_index(op.f('ix_push_logs_snapshot_id'), 'push_logs', ['snapshot_id'], unique=False)
    # (snapshot_id, seq) 复合索引 — 轮询按 seq 升序拿增量
    op.create_index(op.f('ix_push_logs_snapshot_seq'), 'push_logs', ['snapshot_id', 'seq'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_push_logs_snapshot_seq'), table_name='push_logs')
    op.drop_index(op.f('ix_push_logs_snapshot_id'), table_name='push_logs')
    op.drop_index(op.f('ix_push_logs_id'), table_name='push_logs')
    op.drop_table('push_logs')
