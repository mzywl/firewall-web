"""update firewall table

Revision ID: 005_update_firewall
Revises: 004_add_policy_versions
Create Date: 2026-03-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '005_update_firewall'
down_revision = '004_add_policy_versions'
branch_labels = None
depends_on = None


def upgrade():
    # 添加新的枚举值到 FirewallType
    op.execute("ALTER TABLE firewalls MODIFY COLUMN type ENUM('fortigate','hillstone','leadsec','h3c','guanqun','feita','wangshen','other') NOT NULL")
    
    # 重命名和修改列
    op.alter_column('firewalls', 'host', new_column_name='management_ip', existing_type=sa.String(100))
    op.alter_column('firewalls', 'name', type_=sa.String(200), existing_type=sa.String(100))
    
    # 添加新列
    op.add_column('firewalls', sa.Column('alias', sa.String(100), nullable=True, comment='简称/别名'))
    op.add_column('firewalls', sa.Column('connection_type', sa.Enum('ssh', 'api', 'cli', 'manual', name='connectiontype'), nullable=False, server_default='ssh', comment='连接类型'))
    op.add_column('firewalls', sa.Column('connection_config', sa.JSON, nullable=True, comment='连接配置'))
    op.add_column('firewalls', sa.Column('protected_ips', sa.Text, nullable=True, comment='防护IP段'))
    op.add_column('firewalls', sa.Column('supported_policy_types', sa.JSON, nullable=True, comment='支持的策略类型'))
    op.add_column('firewalls', sa.Column('auto_push', sa.Integer, nullable=False, server_default='1', comment='是否支持自动推送'))
    op.add_column('firewalls', sa.Column('push_contact', sa.String(100), nullable=True, comment='推送责任人'))
    op.add_column('firewalls', sa.Column('push_remark', sa.Text, nullable=True, comment='推送备注'))
    op.add_column('firewalls', sa.Column('status', sa.String(20), nullable=False, server_default='enabled', comment='状态'))
    op.add_column('firewalls', sa.Column('remark', sa.Text, nullable=True, comment='备注'))
    
    # 删除旧列
    op.drop_column('firewalls', 'port')
    op.drop_column('firewalls', 'username')
    op.drop_column('firewalls', 'password')
    op.drop_column('firewalls', 'config')


def downgrade():
    # 恢复旧列
    op.add_column('firewalls', sa.Column('port', sa.Integer, server_default='22'))
    op.add_column('firewalls', sa.Column('username', sa.String(100)))
    op.add_column('firewalls', sa.Column('password', sa.String(200)))
    op.add_column('firewalls', sa.Column('config', sa.JSON))
    
    # 删除新列
    op.drop_column('firewalls', 'remark')
    op.drop_column('firewalls', 'status')
    op.drop_column('firewalls', 'push_remark')
    op.drop_column('firewalls', 'push_contact')
    op.drop_column('firewalls', 'auto_push')
    op.drop_column('firewalls', 'supported_policy_types')
    op.drop_column('firewalls', 'protected_ips')
    op.drop_column('firewalls', 'connection_config')
    op.drop_column('firewalls', 'connection_type')
    op.drop_column('firewalls', 'alias')
    
    # 恢复列名
    op.alter_column('firewalls', 'management_ip', new_column_name='host')
    op.alter_column('firewalls', 'name', type_=sa.String(100))
    
    # 恢复枚举
    op.execute("ALTER TABLE firewalls MODIFY COLUMN type ENUM('fortigate','hillstone','leadsec','h3c') NOT NULL")
