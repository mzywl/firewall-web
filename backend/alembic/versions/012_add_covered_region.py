"""ADD Firewall.covered_region column + backfill from region

Revision ID: 012_add_covered_region
Revises: 011_add_policy_system_name
Create Date: 2026-06-19 15:55:00

背景:
  Firewall 表原有 region 字段 (注释: "所属区域"), 实际项目里被两套语义混用:
    1. "防火墙所在区域" (组织归属, 例如 fw14.region="生产区" 表示 fw14 归生产区管)
    2. "防火墙防护区域" (技术防护范围, 例如 fw14 实际防护 10.2.179.0/24 internal 段)

  这个语义混淆导致 preview.py 的 NAT 透传逻辑把 firewall.region (所在区域) 当成
  "防护区域" 用, 出向 SNAT 时转换后 IP 落在对方 region, 但 region_nat_state 用
  fw.covered_region 当 key (fw6.covered_region 默认=测试区), 对方 region 的防火墙
  (如 fw14.region=生产区) 查不到透传状态, 不生成 PASS_THROUGH 行.

本次重构 ADD (不是 RENAME):
  - 新增 covered_region 列 — 表达 "防火墙防护的区域" (技术属性, 跟 region 区分)
  - 保留 region 列 — 表达 "防火墙所在区域" (组织归属)
  - Backfill: covered_region = region (现有数据保持一致, 后续用户/系统可手动调整)

rollback:
  alembic downgrade -1  (只 drop 新列, 旧 region 数据不动)

用法 (运行时 preview.py):
  - 入向 SNAT (source=external): 转换后 src 进入 fw.covered_region (internal 一侧)
    → region_nat_state[fw.covered_region] = {translated_src_ip, ...}
  - 出向 SNAT (source=internal): 转换后 dst 进入对方 region
    → 查 zone_access_configs 找 (firewall_id=fw.id, dest_zone=fw.external_zone_name)
    → 命中后 region_nat_state[cfg.dest_zone] = {translated_dst_ip, ...}
    → cfg.dest_zone 跟对方 firewall.covered_region 一致 (用户配时保证)
  - 非边界墙查 PASS_THROUGH: region_nat_state.get(fw.covered_region)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '012_add_covered_region'
down_revision = '011_add_policy_system_name'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 covered_region 列 + 从 region backfill"""
    # 1) 新增列 (可空, 不破坏老数据读取)
    op.add_column('firewalls', sa.Column(
        'covered_region', sa.String(length=100), nullable=True,
        comment='防护区域 (跟 region "所在区域" 区分: region=组织归属, covered_region=技术防护范围, preview.py NAT 透传 key)'
    ))

    # 2) Backfill: 默认 covered_region = region (现有数据保持一致, 边界墙后续可手动调整)
    op.execute("UPDATE firewalls SET covered_region = region WHERE covered_region IS NULL")


def downgrade() -> None:
    """回滚: drop 新增的 covered_region 列, 旧 region 数据不动"""
    op.drop_column('firewalls', 'covered_region')
