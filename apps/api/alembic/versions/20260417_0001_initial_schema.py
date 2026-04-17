"""Initial schema: norm_source, norm_partition, norm_comma, norm_citation, norm_chunk.

Questa migration crea anche la text-search config `italian_unaccent`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

revision: str = "20260417_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Estensioni — idempotenti.
    for ext in ("uuid-ossp", "pg_trgm", "unaccent", "ltree", "vector", "btree_gin"):
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')

    # Text-search config italian_unaccent.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'italian_unaccent') THEN
            CREATE TEXT SEARCH CONFIGURATION italian_unaccent (COPY = italian);
            ALTER TEXT SEARCH CONFIGURATION italian_unaccent
              ALTER MAPPING FOR hword, hword_part, word WITH unaccent, italian_stem;
          END IF;
        END
        $$;
        """
    )

    # ---- norm_source ----
    op.create_table(
        "norm_source",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("urn", sa.String(256), nullable=False, unique=True),
        sa.Column("short_id", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("issued_at", sa.Date, nullable=False),
        sa.Column("in_force_from", sa.Date, nullable=False),
        sa.Column("in_force_to", sa.Date, nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("source_hash", sa.String(128), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    # ---- norm_partition ----
    op.create_table(
        "norm_partition",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("norm_source.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("norm_partition.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("number", sa.String(32), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("path", sa.String(512), nullable=False),   # serializzato da ltree
        sa.Column("citation", sa.String(256), nullable=False),
        sa.Column("rubrica", sa.Text, nullable=True),
        sa.Column("full_text", sa.Text, nullable=True),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "kind IN ('libro','titolo','capo','sezione','articolo','disposizione-transitoria')",
            name="norm_partition_kind_check",
        ),
    )
    op.create_index(
        "ix_norm_partition_source_kind_number",
        "norm_partition",
        ["source_id", "kind", "number"],
    )
    # Conversione manuale a ltree e indice GiST (ltree non è un tipo SA-supportato nativo)
    op.execute("ALTER TABLE norm_partition ALTER COLUMN path TYPE ltree USING path::ltree")
    op.execute("CREATE INDEX ix_norm_partition_path ON norm_partition USING gist(path)")

    # ---- norm_comma ----
    op.create_table(
        "norm_comma",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("partition_id", UUID(as_uuid=True), sa.ForeignKey("norm_partition.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("number", sa.String(32), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("letters", JSONB, nullable=True),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.UniqueConstraint("partition_id", "ordinal", "effective_from", name="uq_norm_comma_partition_ordinal_effective"),
    )

    # ---- norm_citation ----
    op.create_table(
        "norm_citation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("from_partition_id", UUID(as_uuid=True), sa.ForeignKey("norm_partition.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_comma_id", UUID(as_uuid=True), sa.ForeignKey("norm_comma.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_partition_id", UUID(as_uuid=True), sa.ForeignKey("norm_partition.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_source_id", UUID(as_uuid=True), sa.ForeignKey("norm_source.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("citation_kind", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
    )
    op.create_index("ix_norm_citation_from", "norm_citation", ["from_partition_id"])
    op.create_index("ix_norm_citation_to", "norm_citation", ["to_partition_id"])

    # ---- norm_chunk ----
    op.create_table(
        "norm_chunk",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("partition_id", UUID(as_uuid=True), sa.ForeignKey("norm_partition.id", ondelete="CASCADE"), nullable=False),
        sa.Column("comma_id", UUID(as_uuid=True), sa.ForeignKey("norm_comma.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chunk_kind", sa.String(32), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "text_tsv",
            TSVECTOR,
            sa.Computed("to_tsvector('italian_unaccent', text)", persisted=True),
        ),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("qdrant_point_id", UUID(as_uuid=True), nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_norm_chunk_partition", "norm_chunk", ["partition_id"])
    op.create_index("ix_norm_chunk_tsv", "norm_chunk", ["text_tsv"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_norm_chunk_tsv", table_name="norm_chunk")
    op.drop_index("ix_norm_chunk_partition", table_name="norm_chunk")
    op.drop_table("norm_chunk")
    op.drop_index("ix_norm_citation_to", table_name="norm_citation")
    op.drop_index("ix_norm_citation_from", table_name="norm_citation")
    op.drop_table("norm_citation")
    op.drop_table("norm_comma")
    op.execute("DROP INDEX IF EXISTS ix_norm_partition_path")
    op.drop_index("ix_norm_partition_source_kind_number", table_name="norm_partition")
    op.drop_table("norm_partition")
    op.drop_table("norm_source")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS italian_unaccent")
