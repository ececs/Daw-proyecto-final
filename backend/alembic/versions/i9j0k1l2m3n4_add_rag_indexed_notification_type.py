"""add rag_indexed notification type

Revision ID: i9j0k1l2m3n4
Revises: 0a14b558cb80
Create Date: 2026-05-14 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "i9j0k1l2m3n4"
down_revision = "0a14b558cb80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'rag_indexed'"
    )


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally omitted to keep the
    # migration simple and safe for production data.
    pass
