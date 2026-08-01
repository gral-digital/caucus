"""Modelli SQLAlchemy per gerarchia normativa italiana.

Vedi docs/DATA_MODEL.md per il razionale e la semantica.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from caucus_api.db.base import Base


class NormSource(Base):
    __tablename__ = "norm_source"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    urn: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    short_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    issued_at: Mapped[date] = mapped_column(Date, nullable=False)
    in_force_from: Mapped[date] = mapped_column(Date, nullable=False)
    in_force_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    partitions: Mapped[list[NormPartition]] = relationship(back_populates="source")


class NormPartition(Base):
    __tablename__ = "norm_partition"
    __table_args__ = (
        Index("ix_norm_partition_source_kind_number", "source_id", "kind", "number"),
        # path è VARCHAR (non ltree) in Fase 1 — vedi commento nella migration.
        Index(
            "ix_norm_partition_path",
            "path",
            postgresql_using="gin",
            postgresql_ops={"path": "gin_trgm_ops"},
        ),
        CheckConstraint(
            "kind IN ('libro','titolo','capo','sezione','articolo','disposizione-transitoria')",
            name="norm_partition_kind_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("norm_source.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("norm_partition.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    number: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    # ltree colonna: SQLAlchemy non ha tipo nativo, usiamo String + cast in SQL.
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    citation: Mapped[str] = mapped_column(String(256), nullable=False)
    rubrica: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )

    source: Mapped[NormSource] = relationship(back_populates="partitions")
    parent: Mapped[NormPartition | None] = relationship(
        remote_side="NormPartition.id", back_populates="children"
    )
    children: Mapped[list[NormPartition]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    commi: Mapped[list[NormComma]] = relationship(
        back_populates="partition", cascade="all, delete-orphan"
    )


class NormComma(Base):
    __tablename__ = "norm_comma"
    __table_args__ = (
        UniqueConstraint(
            "partition_id",
            "ordinal",
            "effective_from",
            name="uq_norm_comma_partition_ordinal_effective",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("norm_partition.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    letters: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    partition: Mapped[NormPartition] = relationship(back_populates="commi")


class NormCitation(Base):
    __tablename__ = "norm_citation"
    __table_args__ = (
        Index("ix_norm_citation_from", "from_partition_id"),
        Index("ix_norm_citation_to", "to_partition_id"),
        Index("ix_norm_citation_target_ref", "to_source_short_id", "to_article_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_partition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("norm_partition.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_comma_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("norm_comma.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_partition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("norm_partition.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("norm_source.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    citation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
    # Target denormalizzato: sopravvive al delete-and-replace della fonte
    # target (che azzera to_partition_id via FK SET NULL) e permette la
    # ri-risoluzione del link a ogni load.
    to_source_short_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_article_number: Mapped[str | None] = mapped_column(String(32), nullable=True)


class NormChunk(Base):
    __tablename__ = "norm_chunk"
    __table_args__ = (
        # FTS: generated tsvector con config italian_unaccent (creata nella migration).
        Index(
            "ix_norm_chunk_tsv",
            "text_tsv",
            postgresql_using="gin",
        ),
        Index("ix_norm_chunk_partition", "partition_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("norm_partition.id", ondelete="CASCADE"),
        nullable=False,
    )
    comma_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("norm_comma.id", ondelete="SET NULL"),
        nullable=True,
    )
    chunk_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Generated column: tsvector su text usando config italian_unaccent.
    text_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('italian_unaccent', text)", persisted=True),
    )

    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    qdrant_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CaseLaw(Base):
    """Sentenza/ordinanza di Cassazione (fonte: SentenzeWeb, testo anonimizzato)."""

    __tablename__ = "case_law"
    __table_args__ = (
        Index("ix_case_law_kind_anno_numero", "kind", "anno", "numero"),
        Index("ix_case_law_data_deposito", "data_deposito"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    tipoprov: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sezione: Mapped[str | None] = mapped_column(String(8), nullable=True)
    numero: Mapped[str] = mapped_column(String(16), nullable=False)
    anno: Mapped[int] = mapped_column(Integer, nullable=False)
    ecli: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_decisione: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_deposito: Mapped[date | None] = mapped_column(Date, nullable=True)
    presidente: Mapped[str | None] = mapped_column(Text, nullable=True)
    relatore: Mapped[str | None] = mapped_column(Text, nullable=True)
    materia: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispositivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chunks: Mapped[list[CaseLawChunk]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class CaseLawChunk(Base):
    __tablename__ = "case_law_chunk"
    __table_args__ = (
        Index("ix_case_law_chunk_case", "case_id"),
        Index("ix_case_law_chunk_tsv", "text_tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_law.id", ondelete="CASCADE"), nullable=False
    )
    chunk_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('italian_unaccent', text)", persisted=True),
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    qdrant_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )

    case: Mapped[CaseLaw] = relationship(back_populates="chunks")


class UserDocument(Base):
    """Documento caricato dall'utente per l'analisi (contratto, atto, verbale).

    v1: testo estratto all'upload e conservato in Postgres; il file originale
    non viene salvato. Nessun legame con una "conversazione" persistente
    (che ancora non esiste): il client referenzia i documenti per id nei
    turni di chat.
    """

    __tablename__ = "user_document"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # True se il testo è stato tagliato al cap di ingestione: il modello deve
    # saperlo per non fingere di aver letto il documento intero.
    truncated: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Attributo di sicurezza per la tenancy futura: popolato server-side.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Proprietario (free tier con account): NULL nel self-hosting single-tenant.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserAccount(Base):
    """Account utente per il free tier hosted.

    Nel self-hosting single-tenant gli account restano disattivati
    (``ACCOUNTS_ENABLED=false``, default): l'API funziona come oggi.
    """

    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sempre lowercase (normalizzata alla registrazione): l'unicità è
    # case-insensitive di fatto.
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # Argon2id — mai altri schemi: niente password in chiaro da nessuna parte.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    """Sessione bearer: nel DB vive SOLO l'hash SHA-256 del token opaco."""

    __tablename__ = "auth_session"
    __table_args__ = (Index("ix_auth_session_user", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[UserAccount] = relationship(back_populates="sessions")
