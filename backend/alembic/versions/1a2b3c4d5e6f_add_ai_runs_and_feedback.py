"""add_ai_runs_and_feedback

Revision ID: 1a2b3c4d5e6f
Revises: aa9501823b21
Create Date: 2026-05-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "1a2b3c4d5e6f"
down_revision = "aa9501823b21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=True),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("surface", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("used_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("tool_actions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rag_queries_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rag_hits_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_runs_surface"), "ai_runs", ["surface"], unique=False)
    op.create_index(op.f("ix_ai_runs_thread_id"), "ai_runs", ["thread_id"], unique=False)
    op.create_index(op.f("ix_ai_runs_ticket_id"), "ai_runs", ["ticket_id"], unique=False)
    op.create_index(op.f("ix_ai_runs_user_id"), "ai_runs", ["user_id"], unique=False)

    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_run_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("helped", sa.Boolean(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_run_id"], ["ai_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_run_id", "user_id", name="uq_ai_feedback_run_user"),
    )
    op.create_index(op.f("ix_ai_feedback_ai_run_id"), "ai_feedback", ["ai_run_id"], unique=False)
    op.create_index(op.f("ix_ai_feedback_user_id"), "ai_feedback", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_feedback_user_id"), table_name="ai_feedback")
    op.drop_index(op.f("ix_ai_feedback_ai_run_id"), table_name="ai_feedback")
    op.drop_table("ai_feedback")
    op.drop_index(op.f("ix_ai_runs_user_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_ticket_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_thread_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_surface"), table_name="ai_runs")
    op.drop_table("ai_runs")
