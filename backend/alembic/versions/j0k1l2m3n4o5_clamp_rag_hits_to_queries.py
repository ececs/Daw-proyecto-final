"""clamp ai_runs.rag_hits_count to rag_queries_count

Older rows stored len(chunks) as hits (e.g. 5 per query) instead of the
semantically-correct "did this query return any results?" (0 or 1), which made
the RAG hit rate exceed 100%. This migration brings historical data back into
the [0, queries] range so aggregate panels read correctly.

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-05-14 00:00:00.000000
"""

from alembic import op


revision = "j0k1l2m3n4o5"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE ai_runs "
        "SET rag_hits_count = LEAST(rag_hits_count, rag_queries_count) "
        "WHERE rag_hits_count > rag_queries_count"
    )


def downgrade() -> None:
    # Original inflated values are lost; nothing to restore.
    pass
