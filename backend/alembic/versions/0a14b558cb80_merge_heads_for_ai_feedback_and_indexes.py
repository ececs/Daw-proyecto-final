"""merge heads for ai feedback and indexes

Revision ID: 0a14b558cb80
Revises: 1a2b3c4d5e6f, h8i9j0k1l2m3
Create Date: 2026-05-10 18:23:19.294593+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a14b558cb80'
down_revision: Union[str, None] = ('1a2b3c4d5e6f', 'h8i9j0k1l2m3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
