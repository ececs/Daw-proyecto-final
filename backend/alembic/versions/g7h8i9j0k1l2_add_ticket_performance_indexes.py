"""add ticket performance indexes

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-10 00:00:00.000000

Why:
  Without indexes on filter/sort columns, every query does a sequential scan
  of the full tickets table. At 100 tickets the overhead is barely noticeable;
  at 1000-10000 it becomes the dominant cost of every page load.

  Indexes added:
    - status        : most common filter (kanban columns, table filter)
    - priority      : second most common filter
    - assignee_id   : FK filter (already has FK constraint, not an index)
    - created_at    : default sort column
    - updated_at    : alternative sort column
    - (status, created_at) composite: covers the most common query pattern —
      filter by status then sort by date — in a single index scan.
"""

from alembic import op


# revision identifiers
revision = "g7h8i9j0k1l2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_assignee_id", "tickets", ["assignee_id"])
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
    op.create_index("ix_tickets_updated_at", "tickets", ["updated_at"])
    op.create_index("ix_tickets_status_created_at", "tickets", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tickets_status_created_at", table_name="tickets")
    op.drop_index("ix_tickets_updated_at", table_name="tickets")
    op.drop_index("ix_tickets_created_at", table_name="tickets")
    op.drop_index("ix_tickets_assignee_id", table_name="tickets")
    op.drop_index("ix_tickets_priority", table_name="tickets")
    op.drop_index("ix_tickets_status", table_name="tickets")
