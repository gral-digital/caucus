"""Schema della gerarchia normativa italiana.

Struttura:
    NormSource  (es. Codice Civile)
      └── NormPartition  (libro/titolo/capo/sezione/articolo)
            └── NormComma  (commi di un articolo)

Vedi docs/DATA_MODEL.md per il razionale e la tassonomia delle fonti.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NormSourceType(StrEnum):
    """Tipo di fonte normativa."""

    CODICE = "codice"
    LEGGE = "legge"
    DLGS = "dlgs"
    DL = "dl"
    DPR = "dpr"
    COST = "cost"
    TUE = "tue"
    TFUE = "tfue"
    REG_UE = "reg-ue"
    DIR_UE = "dir-ue"
    DEONT = "deont"


class NormPartitionKind(StrEnum):
    """Livello nella gerarchia della norma."""

    LIBRO = "libro"
    TITOLO = "titolo"
    CAPO = "capo"
    SEZIONE = "sezione"
    ARTICOLO = "articolo"
    DISPOSIZIONE_TRANSITORIA = "disposizione-transitoria"


class NormChunkKind(StrEnum):
    """Tipologia di chunk indicizzato."""

    ARTICOLO_FULL = "articolo-full"
    COMMA = "comma"
    RUBRICA = "rubrica"
    WINDOW = "window"


class NormSource(BaseModel):
    """Fonte normativa radice (un codice, una legge, un d.lgs.)."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    urn: str = Field(..., description="URN nir della fonte, es. 'urn:nir:stato:codice.civile'")
    short_id: str = Field(..., description="Identificatore breve, es. 'cc', 'cp', 'dlgs-231-2001'")
    title: str
    type: NormSourceType
    issued_at: date
    in_force_from: date
    in_force_to: date | None = None
    source_url: str | None = None
    source_hash: str | None = Field(
        None, description="SHA-256 dell'ultimo snapshot dell'intera fonte"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime | None = None
    updated_at: datetime | None = None


class NormPartition(BaseModel):
    """Nodo della gerarchia normativa (libro/titolo/capo/sezione/articolo)."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    source_id: UUID
    parent_id: UUID | None = None
    kind: NormPartitionKind
    number: str = Field(
        ...,
        description="Numero preservato come stringa; supporta 'bis', 'ter', numeri romani.",
        examples=["I", "2043", "570-bis"],
    )
    label: str = Field(..., description="Etichetta umana, es. 'Libro IV — Delle obbligazioni'.")
    ordinal: int = Field(..., ge=0, description="Ordine nel genitore, per sorting stabile")
    path: str = Field(
        ...,
        description="ltree materialized path, es. 'cc.libro_iv.titolo_ix.capo_i.art_2043'.",
    )
    citation: str = Field(
        ..., description="Forma canonica display, es. 'art. 2043 c.c.'."
    )
    rubrica: str | None = None
    full_text: str | None = Field(
        None, description="Testo completo; popolato solo per partizioni foglia (articoli)."
    )
    effective_from: date
    effective_to: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormCommaLetter(BaseModel):
    """Lettera di un comma (es. 'a)', 'b)')."""

    letter: str
    text: str
    numbers: list[dict[str, str]] | None = Field(
        None,
        description="Sotto-numerazioni '1)', '2)' dentro la lettera, se presenti.",
    )


class NormComma(BaseModel):
    """Comma di un articolo. Entità separata per permettere chunking/citazioni granulari."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    partition_id: UUID = Field(..., description="FK a NormPartition dove kind='articolo'")
    ordinal: int = Field(..., ge=0)
    number: str = Field(..., description="Es. '1', '1-bis', '2'")
    text: str
    letters: list[NormCommaLetter] | None = None
    effective_from: date
    effective_to: date | None = None


class NormChunk(BaseModel):
    """Unità indicizzata. Stesso id punta a un point in Qdrant."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    partition_id: UUID
    comma_id: UUID | None = None
    chunk_kind: NormChunkKind
    text: str
    token_count: int
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Payload identico a quello in Qdrant per ogni point.",
    )
