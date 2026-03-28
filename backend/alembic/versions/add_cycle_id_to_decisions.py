"""add cycle_id to decisions

Revision ID: b1c2d3e4f5a6
Revises: 347af0092a8c
Create Date: 2026-03-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '347af0092a8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("cycle_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "cycle_id")
