"""add funding_account_id to recurring_bills

Revision ID: 002
Revises: 001
Create Date: 2026-11-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recurring_bills",
        sa.Column("funding_account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_recurring_bills_funding_account_id",
        "recurring_bills",
        "accounts",
        ["funding_account_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_recurring_bills_funding_account_id",
        "recurring_bills",
        type_="foreignkey",
    )
    op.drop_column("recurring_bills", "funding_account_id")
