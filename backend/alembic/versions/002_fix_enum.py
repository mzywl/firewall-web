"""Fix enum types

Revision ID: 002_fix_enum
Revises: 001_initial
Create Date: 2026-03-05 17:55:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_fix_enum'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 删除旧的枚举类型（如果存在）
    op.execute("DROP TYPE IF EXISTS orderstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS firewalltype CASCADE")
    
    # 重新创建枚举类型
    op.execute("CREATE TYPE orderstatus AS ENUM ('pending', 'processing', 'completed', 'failed')")
    op.execute("CREATE TYPE firewalltype AS ENUM ('fortigate', 'hillstone', 'leadsec', 'h3c')")
    
    # 如果表已存在，更新列类型
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'orders') THEN
                ALTER TABLE orders ALTER COLUMN status TYPE orderstatus USING status::text::orderstatus;
            END IF;
        END $$;
    """)
    
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'firewalls') THEN
                ALTER TABLE firewalls ALTER COLUMN type TYPE firewalltype USING type::text::firewalltype;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    pass
