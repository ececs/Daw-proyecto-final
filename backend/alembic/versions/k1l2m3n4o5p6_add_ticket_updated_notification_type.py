"""add ticket_updated notification type

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-05-16

The backend persists `NotificationType.ticket_updated` when priority or
general ticket updates are broadcast. PostgreSQL enum values must be added
explicitly so production matches the SQLAlchemy model and service layer.
"""

from alembic import op


revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'ticket_updated'"
    )


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally omitted to avoid
    # destructive rewrites of production data.
    pass
