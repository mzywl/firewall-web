"""Fix service field type

Revision ID: 003_fix_service_type
Revises: 002_fix_enum
Create Date: 2026-03-06 10:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_fix_service_type'
down_revision = '002_fix_enum'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 修改 policies 表的 service 字段类型
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'policies') THEN
                ALTER TABLE policies ALTER COLUMN service TYPE VARCHAR(500);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    pass
