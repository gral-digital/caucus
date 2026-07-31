"""Documenti caricati dall'utente per l'analisi documentale.

``user_document`` = testo estratto all'upload (il file originale non viene
conservato in v1); referenziato per id dai turni di chat.

Revision ID: 20260731_0004
Revises: 20260731_0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260731_0004"
down_revision: str | None = "20260731_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_document",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("char_count", sa.Integer, nullable=False),
        sa.Column("truncated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_user_document_created", "user_document", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_document_created", table_name="user_document")
    op.drop_table("user_document")
