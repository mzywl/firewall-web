"""add region zone and nat fields

Revision ID: 007_add_region_zone_nat
Revises: 006_add_firewall_types
Create Date: 2026-03-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007_add_region_zone_nat'
down_revision = '006_add_firewall_types'
branch_labels = None
depends_on = None


def upgrade():
    # 添加区域信息字段
    op.add_column('firewalls', sa.Column('region', sa.String(100), nullable=True, comment='所属区域'))
    op.add_column('firewalls', sa.Column('local_zone_name', sa.String(100), nullable=True, comment='本地防护区域名称'))
    op.add_column('firewalls', sa.Column('external_zone_name', sa.String(100), nullable=True, comment='外部防护区域名称'))
    
    # 重命名 protected_ips 为 internal_protected_ips
    op.alter_column('firewalls', 'protected_ips', new_column_name='internal_protected_ips')
    
    # 添加外部防护IP段
    op.add_column('firewalls', sa.Column('external_protected_ips', sa.Text, nullable=True, comment='外部防护IP段'))
    
    # 添加NAT配置字段
    op.add_column('firewalls', sa.Column('outbound_snat_pool', sa.Text, nullable=True, comment='出向SNAT地址段/地址池名称'))
    op.add_column('firewalls', sa.Column('inbound_dnat_pool', sa.Text, nullable=True, comment='入向DNAT地址段/地址池名称'))
    op.add_column('firewalls', sa.Column('inbound_snat_pool', sa.Text, nullable=True, comment='入向SNAT地址段/地址池名称'))
    op.add_column('firewalls', sa.Column('outbound_dnat_pool', sa.Text, nullable=True, comment='出向DNAT地址段/地址池名称'))


def downgrade():
    # 删除NAT配置字段
    op.drop_column('firewalls', 'outbound_dnat_pool')
    op.drop_column('firewalls', 'inbound_snat_pool')
    op.drop_column('firewalls', 'inbound_dnat_pool')
    op.drop_column('firewalls', 'outbound_snat_pool')
    
    # 删除外部防护IP段
    op.drop_column('firewalls', 'external_protected_ips')
    
    # 重命名回 protected_ips
    op.alter_column('firewalls', 'internal_protected_ips', new_column_name='protected_ips')
    
    # 删除区域信息字段
    op.drop_column('firewalls', 'external_zone_name')
    op.drop_column('firewalls', 'local_zone_name')
    op.drop_column('firewalls', 'region')
