"""Parser Normattiva.

Normattiva espone i testi normativi in due formati principali:
- **AkomaNtoso XML** (preferito quando disponibile sulle URN nir)
- HTML (fallback)

Questa prima implementazione è un *parser scaffold*: gestisce l'estrazione
strutturale dal HTML pubblico di Normattiva per i codici. Il parser XML è
agganciato ma marcato TODO — si attiva quando si ha un campione della risposta
AkomaNtoso dell'URN target (varia leggermente tra atti).

Riferimenti URN:
    urn:nir:stato:codice.civile
    urn:nir:stato:codice.penale
    urn:nir:stato:costituzione
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

import httpx
import structlog
from bs4 import BeautifulSoup, Tag

from avvocato_ingestion.canonical import (
    CanonicalAct,
    CanonicalComma,
    CanonicalCommaLetter,
    CanonicalPartition,
)
from avvocato_rag_core.schemas.norm import NormPartitionKind, NormSourceType

logger = structlog.get_logger(__name__)


URN_CATALOG: dict[str, dict[str, str]] = {
    "cc": {
        "urn": "urn:nir:stato:codice.civile",
        "title": "Codice Civile",
        "issued_at": "1942-03-16",
        "in_force_from": "1942-04-21",
    },
    "cp": {
        "urn": "urn:nir:stato:codice.penale",
        "title": "Codice Penale",
        "issued_at": "1930-10-19",
        "in_force_from": "1931-07-01",
    },
    "cpc": {
        "urn": "urn:nir:stato:codice.procedura.civile",
        "title": "Codice di Procedura Civile",
        "issued_at": "1940-10-28",
        "in_force_from": "1942-04-21",
    },
    "cpp": {
        "urn": "urn:nir:stato:codice.procedura.penale",
        "title": "Codice di Procedura Penale",
        "issued_at": "1988-09-22",
        "in_force_from": "1989-10-24",
    },
    "cost": {
        "urn": "urn:nir:stato:costituzione",
        "title": "Costituzione della Repubblica Italiana",
        "issued_at": "1947-12-27",
        "in_force_from": "1948-01-01",
    },
}


_COMMA_SPLIT_RE = re.compile(r"^\s*(\d+(?:-bis|-ter|-quater|-quinquies)?)\s*\.\s*", re.MULTILINE)
_LETTER_SPLIT_RE = re.compile(r"^\s*([a-z])\)\s+", re.MULTILINE)


class NormattivaParser:
    """Fetch + parse di un codice da Normattiva.

    Usa HTML pubblico; rispetta rate-limit e user-agent identificabile.
    Per produzione, sostituire con il parser AkomaNtoso XML quando disponibile
    per l'URN (più robusto).
    """

    BASE_URL = "https://www.normattiva.it/uri-res/N2Ls"

    def __init__(
        self,
        *,
        user_agent: str,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._http = http_client or httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept-Language": "it-IT"},
            timeout=timeout,
            follow_redirects=True,
        )

    async def fetch_codice(self, short_id: str) -> CanonicalAct:
        """Scarica e parsa un codice (short_id = 'cc', 'cp', 'cpc', 'cpp', 'cost')."""
        if short_id not in URN_CATALOG:
            raise ValueError(f"Unknown codice short_id: {short_id!r}")

        entry = URN_CATALOG[short_id]
        urn = entry["urn"]
        logger.info("normattiva.fetch", urn=urn)

        resp = await self._http.get(self.BASE_URL, params={"urn": urn})
        resp.raise_for_status()
        html = resp.text
        source_hash = hashlib.sha256(html.encode()).hexdigest()

        # TODO: il parser HTML di Normattiva richiede una fase successiva di navigazione
        # articolo-per-articolo perché la home di un codice elenca solo le partizioni top-level.
        # Per una prima PoC fidabile useremo il percorso di drilldown: ogni articolo ha un
        # link proprio del tipo ?urn=urn:nir:stato:codice.civile!vig~art2043
        root = self._parse_index(html)

        return CanonicalAct(
            urn=urn,
            short_id=short_id,
            title=entry["title"],
            type=NormSourceType.CODICE,
            issued_at=date.fromisoformat(entry["issued_at"]),
            in_force_from=date.fromisoformat(entry["in_force_from"]),
            in_force_to=None,
            source_url=f"{self.BASE_URL}?urn={urn}",
            source_hash=source_hash,
            root=root,
        )

    # ------------------------------------------------------------------
    # Parser internals (HTML)
    # ------------------------------------------------------------------

    def _parse_index(self, html: str) -> list[CanonicalPartition]:
        """Estrae l'indice delle partizioni top-level.

        NB: questa è una prima approssimazione — Normattiva serve un DOM complesso con
        div annidati che rappresentano libri/titoli/capi/articoli. Quando si avrà un
        AkomaNtoso XML usabile via URN, sostituire con il parser XML più robusto.
        """
        soup = BeautifulSoup(html, "lxml")
        # Placeholder: estrae almeno il title e ritorna struttura vuota.
        # Il parser completo verrà popolato quando agganceremo un campione
        # AkomaNtoso reale e test su golden set (es. conteggio 2969 articoli CC).
        logger.warning(
            "normattiva.parse_index.placeholder",
            note="HTML parser è scaffold; sostituire con AkomaNtoso XML prima del go-live.",
        )
        return []

    @staticmethod
    def split_commi(full_text: str) -> list[CanonicalComma]:
        """Divide il testo di un articolo in commi usando la numerazione 'N.'.

        Funziona su articoli ben formattati (majority dei codici). Articoli con
        struttura anomala vanno revisionati a mano.
        """
        if not full_text.strip():
            return []

        matches = list(_COMMA_SPLIT_RE.finditer(full_text))
        if not matches:
            # Articolo con un solo comma, numerazione assente.
            return [CanonicalComma(number="1", text=full_text.strip())]

        out: list[CanonicalComma] = []
        for idx, match in enumerate(matches):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
            text = full_text[start:end].strip()
            out.append(
                CanonicalComma(
                    number=match.group(1),
                    text=text,
                    letters=NormattivaParser._split_letters(text),
                )
            )
        return out

    @staticmethod
    def _split_letters(text: str) -> list[CanonicalCommaLetter] | None:
        matches = list(_LETTER_SPLIT_RE.finditer(text))
        if not matches:
            return None
        out: list[CanonicalCommaLetter] = []
        for idx, match in enumerate(matches):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            out.append(CanonicalCommaLetter(letter=match.group(1), text=text[start:end].strip()))
        return out

    async def aclose(self) -> None:
        await self._http.aclose()


# ----------------------------------------------------------------------
# Discoverable helpers (placeholder) per scraping per-articolo
# ----------------------------------------------------------------------

def build_article_urn(codice_short_id: str, article_num: str) -> str:
    """Compone l'URN NIR per un articolo specifico di un codice."""
    base_urn = URN_CATALOG[codice_short_id]["urn"]
    # Normattiva accetta la forma `!vig~artN` per il testo vigente.
    return f"{base_urn}!vig~art{article_num}"


# Il parser AkomaNtoso (preferito) va implementato qui quando si hanno campioni.
# Lo stub qui sotto mostra la firma attesa.

def parse_akoma_ntoso(xml: str, short_id: str) -> CanonicalAct:  # noqa: ARG001
    raise NotImplementedError(
        "Parser AkomaNtoso da implementare con un campione XML dell'URN target. "
        "Vedi docs/INGESTION.md §2 per approccio."
    )
