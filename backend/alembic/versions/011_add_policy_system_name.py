"""ADD Policy.source_system_name / dest_system_name columns + backfill from source_zone/dest_zone

Revision ID: 011_add_policy_system_name
Revises: 010_remove_dnat
Create Date: 2026-06-19 13:55:00

背景:
  Policy 表原本只有 source_zone / dest_zone 两列, 旧代码误用这两列存 Excel 解析出的
  业务系统名 (如 "vas-prod-app02"), 但列名"zone"暗示的是 internal/external 网络 zone 概念,
  语义混淆。

  本次重构 ADD (不是 RENAME):
  - 新增 source_system_name / dest_system_name 列 — 存 Excel 解析出的业务系统名
  - 保留 source_zone / dest_zone 列 — 给 firewall_matcher 写网络 zone 分类 (internal/external)
  - Backfill: 把现有 source_zone / dest_zone 数据复制到 source_system_name / dest_system_name
    (旧数据虽然语义错位, 但值就是系统名, 复制过去刚好)
  - 不清空 source_zone / dest_zone — 历史保留, firewall_matcher 后续可覆盖

rollback:
  alembic downgrade -1  (只 drop 新列, 旧列数据不动)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '011_add_policy_system_name'
down_revision = '010_remove_dnat'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 source_system_name / dest_system_name 列 + 从旧 source_zone / dest_zone backfill"""
    # 1) 新增列 (可空, 不破坏老数据读取)
    op.add_column('policies', sa.Column('source_system_name', sa.String(length=100), nullable=True,
                                        comment='源系统名(业务归属,Excel 解析)'))
    op.add_column('policies', sa.Column('dest_system_name', sa.String(length=100), nullable=True,
                                        comment='目的系统名(业务归属,Excel 解析)'))

    # 2) Backfill: 旧 source_zone / dest_zone 存的就是业务系统名 (历史误用)
    #    复制过去保证新字段有值, 老字段保留
    op.execute("UPDATE policies SET source_system_name = source_zone WHERE source_system_name IS NULL")
    op.execute("UPDATE policies SET dest_system_name = dest_zone WHERE dest_system_name IS NULL")


def downgrade() -> None:
    """回滚: drop 新增的两列, 旧 source_zone / dest_zone 数据不动"""
    op.drop_column('policies', 'source_system_name')
    op.drop_column('policies', 'dest_system_name')
