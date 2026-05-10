"""add comment and attachment ticket_id indexes

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-05-10 00:00:00.000000

Why:
  comments.ticket_id and attachments.ticket_id are foreign keys without
  an index. Every GET /tickets/{id}/comments and /attachments query
  does a sequential scan of the full table, even though it returns only
  the rows for one ticket. At 10k+ rows this dominates the response time
  of the ticket detail page.
"""

from alembic import op


revision = "h8i9j0k1l2m3"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_comments_ticket_id", "comments", ["ticket_id"])
    op.create_index("ix_attachments_ticket_id", "attachments", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_ticket_id", table_name="attachments")
    op.drop_index("ix_comments_ticket_id", table_name="comments")
