"""Modello canonico (intermedio) per un atto normativo parsato.

I parser (Normattiva XML, Normattiva HTML, CED, …) producono `CanonicalAct`.
Il loader persiste SOLO questa struttura — così cambiare parser non tocca il
layer di persistenza.
"""

from __future__ import annotations

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from avvocato_rag_core.schemas.norm import NormPartitionKind, NormSourceType


class CanonicalCommaLetter(BaseModel):
    model_config = ConfigDict(frozen=True)
    letter: str
    text: str


class CanonicalComma(BaseModel):
    model_config = ConfigDict(frozen=True)
    number: str
    text: str
    letters: list[CanonicalCommaLetter] | None = None


class CanonicalPartition(BaseModel):
    """Nodo della gerarchia (libro/titolo/capo/sezione/articolo).

    Gli articoli hanno `commi`, gli altri livelli hanno `children`.
    """

    model_config = ConfigDict(frozen=True)

    kind: NormPartitionKind
    number: str
    label: str
    rubrica: str | None = None
    full_text: str | None = None
    commi: list[CanonicalComma] = Field(default_factory=list)
    children: list["CanonicalPartition"] = Field(default_factory=list)

    def walk(self) -> list[Self]:
        """Ritorna flat tree (DFS)."""
        out: list[Self] = [self]
        for c in self.children:
            out.extend(c.walk())
        return out


class CanonicalAct(BaseModel):
    """Fonte normativa parsata completa."""

    model_config = ConfigDict(frozen=True)

    urn: str
    short_id: str
    title: str
    type: NormSourceType
    issued_at: date
    in_force_from: date
    in_force_to: date | None = None
    source_url: str | None = None
    source_hash: str | None = None
    root: list[CanonicalPartition]
