"""Colonne target denormalizzate su norm_citation.

Il loader fa delete-and-replace per fonte: le citazioni provenienti da altre
fonti perdono il ``to_partition_id`` (FK SET NULL) quando la fonte target viene
ricaricata. Con (to_source_short_id, to_article_number) denormalizzati il link
è ri-risolvibile a ogni load senza perdere informazione.

Revision ID: 20260731_0002
Revises: 20260417_0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0002"
down_revision: str | None = "20260417_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "norm_citation",
        sa.Column("to_source_short_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "norm_citation",
        sa.Column("to_article_number", sa.String(32), nullable=True),
    )
    op.create_index(
        "ix_norm_citation_target_ref",
        "norm_citation",
        ["to_source_short_id", "to_article_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_norm_citation_target_ref", table_name="norm_citation")
    op.drop_column("norm_citation", "to_article_number")
    op.drop_column("norm_citation", "to_source_short_id")
