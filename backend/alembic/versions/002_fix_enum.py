"""Fix enum types

Revision ID: 002_fix_enum
Revises: 001_initial
Create Date: 2026-03-05 17:55:00.000000

注意：原版使用 `DROP TYPE ... CASCADE` 会把依赖该类型的列也删掉（orderstatus
类型被删时 orders.status 列也会被 cascade 删除），导致后续 ALTER TABLE 报
"column 'status' does not exist"。

修复思路：枚举类型已经是正确的（001 创建的），本迁移不需要重建；只在类型
不存在时创建，且不破坏已有列。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_fix_enum'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 安全创建枚举类型（如果已存在就跳过，避免破坏依赖列）
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orderstatus') THEN
                CREATE TYPE orderstatus AS ENUM ('pending', 'processing', 'completed', 'failed');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'firewalltype') THEN
                CREATE TYPE firewalltype AS ENUM ('fortigate', 'hillstone', 'leadsec', 'h3c');
            END IF;
        END $$;
    """)

    # 仅当 orders.status 列存在但类型不是 orderstatus enum 时才转换
    # （正常情况下 001 已经建好了正确类型，这里是兜底）
    op.execute("""
        DO $$
        DECLARE
            col_type text;
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables WHERE table_name = 'orders'
            ) AND EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'orders' AND column_name = 'status'
            ) THEN
                SELECT data_type INTO col_type
                FROM information_schema.columns
                WHERE table_name = 'orders' AND column_name = 'status';

                IF col_type IS NOT NULL AND col_type <> 'USER-DEFINED' THEN
                    ALTER TABLE orders
                        ALTER COLUMN status TYPE orderstatus
                        USING status::text::orderstatus;
                END IF;
            END IF;
        END $$;
    """)

    # 同样的兜底：firewalls.type
    op.execute("""
        DO $$
        DECLARE
            col_type text;
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables WHERE table_name = 'firewalls'
            ) AND EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'firewalls' AND column_name = 'type'
            ) THEN
                SELECT data_type INTO col_type
                FROM information_schema.columns
                WHERE table_name = 'firewalls' AND column_name = 'type';

                IF col_type IS NOT NULL AND col_type <> 'USER-DEFINED' THEN
                    ALTER TABLE firewalls
                        ALTER COLUMN type TYPE firewalltype
                        USING type::text::firewalltype;
                END IF;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # 故意不删枚举类型：可能被其他对象引用，硬删会破坏数据库状态
    pass
