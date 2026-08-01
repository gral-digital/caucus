"""Account e sessioni per il free tier hosted + owner dei documenti.

``user_account`` (email unica, hash Argon2id) e ``auth_session`` (solo hash
SHA-256 del token). ``user_document.user_id`` lega i documenti caricati
all'account quando gli account sono attivi (nullable: il self-hosting
single-tenant resta senza account).

Revision ID: 20260731_0005
Revises: 20260731_0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260731_0005"
down_revision: str | None = "20260731_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "auth_session",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=True),
    )
    op.create_index("ix_auth_session_user", "auth_session", ["user_id"])
    op.add_column(
        "user_document",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_user_document_user", "user_document", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_document_user", table_name="user_document")
    op.drop_column("user_document", "user_id")
    op.drop_index("ix_auth_session_user", table_name="auth_session")
    op.drop_table("auth_session")
    op.drop_table("user_account")
