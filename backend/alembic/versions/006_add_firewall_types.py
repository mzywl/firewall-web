"""add new firewall types

Revision ID: 006_add_firewall_types
Revises: 005_update_firewall
Create Date: 2026-03-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006_add_firewall_types'
down_revision = '005_update_firewall'
branch_labels = None
depends_on = None


def upgrade():
    # 创建新的枚举类型，包含新增的防火墙类型
    op.execute("CREATE TYPE firewalltype_new AS ENUM('fortigate','hillstone','leadsec','h3c','guanqun','feita','wangshen','sangfor','huawei','shanshi','other')")
    
    # 更新列的类型
    op.execute("ALTER TABLE firewalls ALTER COLUMN type TYPE firewalltype_new USING type::text::firewalltype_new")
    
    # 删除旧类型
    op.execute("DROP TYPE firewalltype")
    
    # 重命名新类型
    op.execute("ALTER TYPE firewalltype_new RENAME TO firewalltype")


def downgrade():
    # 创建旧的枚举类型
    op.execute("CREATE TYPE firewalltype_old AS ENUM('fortigate','hillstone','leadsec','h3c','guanqun','feita','wangshen','other')")
    
    # 更新列的类型
    op.execute("ALTER TABLE firewalls ALTER COLUMN type TYPE firewalltype_old USING type::text::firewalltype_old")
    
    # 删除新类型
    op.execute("DROP TYPE firewalltype")
    
    # 重命名旧类型
    op.execute("ALTER TYPE firewalltype_old RENAME TO firewalltype")
