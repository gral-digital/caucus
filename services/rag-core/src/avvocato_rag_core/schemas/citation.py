"""Citazioni machine-readable.

Formato canonico usato da LLM, API e UI per riferirsi a norme e sentenze italiane.
Vedi data/schemas/citation.schema.json per lo schema JSON equivalente.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class CitationKind(StrEnum):
    NORM = "norm"
    CASE = "case"


class NormCitation(BaseModel):
    """Citazione a una partizione normativa (articolo, comma, lettera)."""

    model_config = ConfigDict(frozen=True)

    kind: Literal[CitationKind.NORM] = CitationKind.NORM
    source: str = Field(..., description="short_id della fonte, es. 'cc', 'cp', 'dlgs-231-2001'.")
    part: Literal["libro", "titolo", "capo", "sezione", "articolo", "art"] = "art"
    num: str = Field(..., description="Numero preservato come stringa, es. '2043', '570-bis'.")
    comma: str | None = None
    letter: str | None = None
    number: str | None = Field(None, description="Sotto-numero di una lettera (es. '1)', '2)').")
    effective_at: date | None = Field(
        None,
        description="Data per versioning. None = testo vigente.",
    )

    def to_display(self) -> str:
        """Forma display italiana canonica (es. 'art. 2043, c. 1 c.c.')."""
        bits = [f"art. {self.num}"]
        if self.comma:
            bits.append(f"c. {self.comma}")
        if self.letter:
            bits.append(f"lett. {self.letter})")
        bits.append(_source_suffix(self.source))
        return ", ".join(bits[:-1]) + " " + bits[-1]

    def to_anchor(self) -> str:
        """Anchor URL-safe stabile per il frontend, es. 'cc/art/2043#c1'."""
        anchor = f"{self.source}/art/{self.num}"
        fragment = []
        if self.comma:
            fragment.append(f"c{self.comma}")
        if self.letter:
            fragment.append(f"l{self.letter}")
        if fragment:
            anchor += "#" + "-".join(fragment)
        return anchor


class CaseLawCitation(BaseModel):
    """Citazione a una sentenza."""

    model_config = ConfigDict(frozen=True)

    kind: Literal[CitationKind.CASE] = CitationKind.CASE
    court: Literal[
        "cass-civ",
        "cass-pen",
        "cass-su",
        "cost",
        "app",
        "trib",
        "giudice-pace",
        "ced",
    ]
    section: str | None = None
    decision_number: str
    decision_year: int = Field(..., ge=1900, le=2100)

    def to_display(self) -> str:
        court_names = {
            "cass-civ": "Cass. civ.",
            "cass-pen": "Cass. pen.",
            "cass-su": "Cass. Sez. Un.",
            "cost": "Corte cost.",
            "app": "Corte app.",
            "trib": "Trib.",
            "giudice-pace": "G.d.P.",
            "ced": "Cass. (CED)",
        }
        parts = [court_names.get(self.court, self.court)]
        if self.section:
            parts.append(self.section)
        parts.append(f"n. {self.decision_number}/{self.decision_year}")
        return ", ".join(parts)


# Unione discriminata: Pydantic usa 'kind' per dispatchare.
Citation = Annotated[
    NormCitation | CaseLawCitation,
    Field(discriminator="kind"),
]


_SOURCE_SUFFIX = {
    # Codici classici
    "cc": "c.c.",
    "cp": "c.p.",
    "cpc": "c.p.c.",
    "cpp": "c.p.p.",
    "cost": "Cost.",
    # Codici moderni
    "cds": "cod. strada",
    "cdc": "cod. cons.",
    "ccii": "CCII",
    "ccp": "cod. contr. pubbl.",
    "cad": "CAD",
    "cts": "CTS",
    # Testi Unici
    "tus": "TU stup.",
    "tui": "TU imm.",
    "tue": "TU ed.",
    "tusl": "TU sic. lav.",
    "tub": "TUB",
    "tuf": "TUF",
    "tuir": "TUIR",
    # Leggi fondamentali
    "cpriv": "cod. privacy",
    "l241": "L. 241/1990",
    "stat": "St. Lav.",
    "l689": "L. 689/1981",
    "lpf": "L. 247/2012",
    "dlgs231": "D.Lgs. 231/2001",
    "aml": "D.Lgs. 231/2007",
    "l190": "L. 190/2012",
    "dlgs33": "D.Lgs. 33/2013",
    "dlgs39": "D.Lgs. 39/2013",
    "cam": "cod. antimafia",
    "wb": "D.Lgs. 24/2023",
    "ritpag": "D.Lgs. 231/2002",
    "tua": "TU ambiente",
    "tupi": "TU pubbl. imp.",
    "cpa": "c.p.a.",
    "cpt": "D.Lgs. 546/1992",
    "tuel": "TUEL",
    "tudoc": "D.P.R. 445/2000",
    "cbc": "cod. beni cult.",
    "cap": "cod. ass.",
    "iva": "D.P.R. 633/1972",
    "dpr600": "D.P.R. 600/1973",
    "lav81": "D.Lgs. 81/2015",
    "l604": "L. 604/1966",
    "dlgs23": "D.Lgs. 23/2015",
    "tumat": "TU maternità",
    "l392": "L. 392/1978",
    "l898": "L. 898/1970",
    "l76": "L. 76/2016",
    "l91": "L. 91/1992",
    "cnav": "cod. nav.",
    "gdpr": "GDPR",
    "aiact": "AI Act",
    "nis2": "dir. NIS2",
    "dora": "reg. DORA",
    "mica": "reg. MiCA",
    "eidas": "reg. eIDAS",
    "dsa": "reg. DSA",
    "dma": "reg. DMA",
    "dircons": "dir. 2011/83/UE",
    "wbdir": "dir. (UE) 2019/1937",
    "amld": "dir. (UE) 2015/849",
    "psd2": "PSD2",
    "eprivacy": "dir. ePrivacy",
    "mifid2": "MiFID II",
}


def _source_suffix(short_id: str) -> str:
    """Sigla canonica per una fonte (es. 'cc' → 'c.c.')."""
    return _SOURCE_SUFFIX.get(short_id, short_id)
