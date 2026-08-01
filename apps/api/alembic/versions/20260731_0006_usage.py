"""Contatori d'uso giornalieri per le quote del free tier.

Revision ID: 20260731_0006
Revises: 20260731_0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260731_0006"
down_revision: str | None = "20260731_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_daily",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("chat_count", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("usage_daily")
