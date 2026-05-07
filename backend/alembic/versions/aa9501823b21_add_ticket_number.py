"""add_ticket_number

Revision ID: aa9501823b21
Revises: a7b8c9d0e1f2
Create Date: 2026-05-07 22:14:59.236843+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'aa9501823b21'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sequence for ticket numbers
    op.execute("CREATE SEQUENCE IF NOT EXISTS ticket_number_seq START 1")

    # Add column as nullable first so existing rows can be backfilled
    op.add_column("tickets", sa.Column("ticket_number", sa.Integer(), nullable=True))

    # Backfill existing tickets ordered by creation date
    op.execute("""
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at ASC) AS rn
            FROM tickets
        )
        UPDATE tickets SET ticket_number = numbered.rn
        FROM numbered WHERE tickets.id = numbered.id
    """)

    # Advance the sequence past the highest assigned number
    op.execute(
        "SELECT setval('ticket_number_seq', COALESCE((SELECT MAX(ticket_number) FROM tickets), 0))"
    )

    # Set the column default to the sequence, make it NOT NULL, add unique index
    op.execute(
        "ALTER TABLE tickets ALTER COLUMN ticket_number SET DEFAULT nextval('ticket_number_seq')"
    )
    op.alter_column("tickets", "ticket_number", nullable=False)
    op.create_index("ix_tickets_ticket_number", "tickets", ["ticket_number"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tickets_ticket_number", table_name="tickets")
    op.drop_column("tickets", "ticket_number")
    op.execute("DROP SEQUENCE IF EXISTS ticket_number_seq")
