"""add zone_role to firewall_zones

对齐设计文档 §1 spec (防火墙自动化运维系统核心设计方案):

**FirewallZone 表:**
- ADD: zone_role (NN, enum: 'internal' / 'external')
  - 显式标记 zone 是「内部防护域 (Trust)」还是「外部防护域 (Untrust)」
  - 替代现行隐式判定: `connect_region == fw.belong_region`

Backfill 规则 (存量数据):
  - 同一 zone 的 connect_region == firewall.belong_region → 'internal'
  - 其他 (跨大区出口) → 'external'
  - 兜底: 'internal' (NOT NULL 约束)

同时:
- 加复合索引 (firewall_id, zone_role) 加速 chain_planner 按 firewall 筛 internal/external

Revision ID: 014_add_zone_role
Revises: 013_spec_full_alignment
Create Date: 2026-06-22 02:35:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '014_add_zone_role'
down_revision = '013_spec_full_alignment'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """加 zone_role 列 + 存量 backfill + 复合索引"""

    # 1) 加 zone_role 列 (nullable, 先 backfill 再设 NN)
    op.execute("""
        ALTER TABLE firewall_zones
        ADD COLUMN zone_role VARCHAR(20)
    """)

    # 2) Backfill: 用 connect_region vs firewall.belong_region 判定
    #    内部: zone.connect_region == fw.belong_region (默认 trust 区域)
    #    外部: 其他 (通往其他大区的出口)
    op.execute("""
        UPDATE firewall_zones z
        SET zone_role = CASE
            WHEN z.connect_region = f.belong_region THEN 'internal'
            ELSE 'external'
        END
        FROM firewalls f
        WHERE z.firewall_id = f.id AND z.zone_role IS NULL
    """)

    # 3) 兜底: 任何还为 NULL 的 (孤立 zone) 标记 internal
    op.execute("""
        UPDATE firewall_zones
        SET zone_role = 'internal'
        WHERE zone_role IS NULL
    """)

    # 4) 改 NN 约束
    op.alter_column('firewall_zones', 'zone_role', nullable=False)

    # 5) 复合索引: chain_planner 频繁按 firewall 筛 internal/external
    op.create_index(
        'ix_firewall_zones_firewall_id_zone_role',
        'firewall_zones',
        ['firewall_id', 'zone_role'],
    )


def downgrade() -> None:
    """回滚"""
    op.drop_index('ix_firewall_zones_firewall_id_zone_role', 'firewall_zones')
    op.drop_column('firewall_zones', 'zone_role')
