"""Tabelle per la giurisprudenza di Cassazione (SentenzeWeb).

``case_law`` = una sentenza/ordinanza; ``case_law_chunk`` = chunk indicizzati
(FTS + vettori in Qdrant, collection `cassazione`).

Revision ID: 20260731_0003
Revises: 20260731_0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

revision: str = "20260731_0003"
down_revision: str | None = "20260731_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_law",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # id del documento su SentenzeWeb (es. "snpen2026327992S"): chiave di
        # idempotenza per l'harvest incrementale.
        sa.Column("external_id", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),  # snciv | snpen
        sa.Column("tipoprov", sa.String(32), nullable=True),  # Sentenza | Ordinanza | ...
        sa.Column("sezione", sa.String(8), nullable=True),
        sa.Column("numero", sa.String(16), nullable=False),
        sa.Column("anno", sa.Integer, nullable=False),
        sa.Column("ecli", sa.String(64), nullable=True),
        sa.Column("data_decisione", sa.Date, nullable=True),
        sa.Column("data_deposito", sa.Date, nullable=True),
        sa.Column("presidente", sa.Text, nullable=True),
        sa.Column("relatore", sa.Text, nullable=True),
        sa.Column("materia", sa.Text, nullable=True),
        sa.Column("dispositivo", sa.Text, nullable=True),
        sa.Column("full_text", sa.Text, nullable=False),
        sa.Column("filename", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_case_law_kind_anno_numero", "case_law", ["kind", "anno", "numero"])
    op.create_index("ix_case_law_data_deposito", "case_law", ["data_deposito"])

    op.create_table(
        "case_law_chunk",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("case_law.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_kind", sa.String(32), nullable=False),  # testo | dispositivo
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "text_tsv",
            TSVECTOR,
            sa.Computed("to_tsvector('italian_unaccent', text)", persisted=True),
        ),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("qdrant_point_id", UUID(as_uuid=True), nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_case_law_chunk_case", "case_law_chunk", ["case_id"])
    op.create_index("ix_case_law_chunk_tsv", "case_law_chunk", ["text_tsv"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_table("case_law_chunk")
    op.drop_table("case_law")
