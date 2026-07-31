"""Fetcher + parser EUR-Lex per regolamenti e direttive UE in italiano.

Scarica l'HTML ufficiale da EUR-Lex per numero CELEX
(``https://eur-lex.europa.eu/legal-content/IT/TXT/HTML/?uri=CELEX:32016R0679``)
e lo parsa in un ``CanonicalAct`` riusando lo stesso modello canonico — e
quindi lo stesso Loader — della pipeline Normattiva.

NB sul consolidamento: viene fetchato il testo pubblicato in Gazzetta UE
(serie CELEX ``3xxxx``), non il consolidato con emendamenti successivi (serie
``0xxxx``, che richiede la data di consolidamento esatta nel CELEX). Per gli
atti in catalogo il testo base è quello sostanziale; il supporto al
consolidato è un TODO tracciato.

Struttura HTML EUR-Lex (varia per epoca di pubblicazione):
- Articoli marcati da elementi con class ``ti-art`` / ``oj-ti-art``
  (testo "Articolo N").
- Rubrica nell'elemento successivo con class ``sti-art`` / ``oj-sti-art``.
- Corpo: tutto il testo fino al prossimo marcatore di articolo o di allegato.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

import httpx
import structlog
from aiolimiter import AsyncLimiter
from lxml import html as lxml_html

from caucus_ingestion.canonical import (
    CanonicalAct,
    CanonicalComma,
    CanonicalPartition,
)
from caucus_rag_core.schemas.norm import NormPartitionKind, NormSourceType

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EuActInfo:
    short_id: str
    celex: str
    title: str
    type: NormSourceType
    issued_at: date
    in_force_from: date


# Catalogo degli atti UE indicizzati. short_id disgiunti da CODICI_CATALOG.
EURLEX_CATALOG: dict[str, EuActInfo] = {
    "gdpr": EuActInfo(
        short_id="gdpr",
        celex="32016R0679",
        title="Regolamento generale sulla protezione dei dati (GDPR, Reg. UE 2016/679)",
        type=NormSourceType.REG_UE,
        issued_at=date(2016, 4, 27),
        in_force_from=date(2018, 5, 25),
    ),
    "aiact": EuActInfo(
        short_id="aiact",
        celex="32024R1689",
        title="Regolamento sull'intelligenza artificiale (AI Act, Reg. UE 2024/1689)",
        type=NormSourceType.REG_UE,
        issued_at=date(2024, 6, 13),
        in_force_from=date(2024, 8, 1),
    ),
    "nis2": EuActInfo(
        short_id="nis2",
        celex="32022L2555",
        title="Direttiva NIS2 (Dir. UE 2022/2555 — cibersicurezza)",
        type=NormSourceType.DIR_UE,
        issued_at=date(2022, 12, 14),
        in_force_from=date(2023, 1, 16),
    ),
    "dora": EuActInfo(
        short_id="dora",
        celex="32022R2554",
        title="Regolamento DORA (Reg. UE 2022/2554 — resilienza operativa digitale finanziaria)",
        type=NormSourceType.REG_UE,
        issued_at=date(2022, 12, 14),
        in_force_from=date(2025, 1, 17),
    ),
    "mica": EuActInfo(
        short_id="mica",
        celex="32023R1114",
        title="Regolamento MiCA (Reg. UE 2023/1114 — mercati delle cripto-attività)",
        type=NormSourceType.REG_UE,
        issued_at=date(2023, 5, 31),
        in_force_from=date(2024, 12, 30),
    ),
    "eidas": EuActInfo(
        short_id="eidas",
        celex="32014R0910",
        title="Regolamento eIDAS (Reg. UE 910/2014 — identificazione elettronica e servizi fiduciari)",
        type=NormSourceType.REG_UE,
        issued_at=date(2014, 7, 23),
        in_force_from=date(2016, 7, 1),
    ),
    "dsa": EuActInfo(
        short_id="dsa",
        celex="32022R2065",
        title="Regolamento sui servizi digitali (DSA, Reg. UE 2022/2065)",
        type=NormSourceType.REG_UE,
        issued_at=date(2022, 10, 19),
        in_force_from=date(2024, 2, 17),
    ),
    "dma": EuActInfo(
        short_id="dma",
        celex="32022R1925",
        title="Regolamento sui mercati digitali (DMA, Reg. UE 2022/1925)",
        type=NormSourceType.REG_UE,
        issued_at=date(2022, 9, 14),
        in_force_from=date(2023, 5, 2),
    ),
    "dircons": EuActInfo(
        short_id="dircons",
        celex="32011L0083",
        title="Direttiva sui diritti dei consumatori (Dir. 2011/83/UE)",
        type=NormSourceType.DIR_UE,
        issued_at=date(2011, 10, 25),
        in_force_from=date(2014, 6, 13),
    ),
    "wbdir": EuActInfo(
        short_id="wbdir",
        celex="32019L1937",
        title="Direttiva whistleblowing (Dir. UE 2019/1937)",
        type=NormSourceType.DIR_UE,
        issued_at=date(2019, 10, 23),
        in_force_from=date(2019, 12, 16),
    ),
    "amld": EuActInfo(
        short_id="amld",
        celex="32015L0849",
        title="IV Direttiva antiriciclaggio (Dir. UE 2015/849)",
        type=NormSourceType.DIR_UE,
        issued_at=date(2015, 5, 20),
        in_force_from=date(2015, 6, 25),
    ),
    "psd2": EuActInfo(
        short_id="psd2",
        celex="32015L2366",
        title="Direttiva PSD2 (Dir. UE 2015/2366 — servizi di pagamento)",
        type=NormSourceType.DIR_UE,
        issued_at=date(2015, 11, 25),
        in_force_from=date(2018, 1, 13),
    ),
    "eprivacy": EuActInfo(
        short_id="eprivacy",
        celex="32002L0058",
        title="Direttiva ePrivacy (Dir. 2002/58/CE)",
        type=NormSourceType.DIR_UE,
        issued_at=date(2002, 7, 12),
        in_force_from=date(2002, 7, 31),
    ),
    "mifid2": EuActInfo(
        short_id="mifid2",
        celex="32014L0065",
        title="Direttiva MiFID II (Dir. 2014/65/UE — mercati degli strumenti finanziari)",
        type=NormSourceType.DIR_UE,
        issued_at=date(2014, 5, 15),
        in_force_from=date(2018, 1, 3),
    ),
}


class EurlexFetchError(RuntimeError):
    """Errore di fetch EUR-Lex."""


class EurlexFetcher:
    """Client per scaricare il testo HTML italiano di un atto per CELEX."""

    BASE = "https://eur-lex.europa.eu/legal-content/IT/TXT/HTML/"

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 60.0,
        requests_per_second: float = 1.0,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        self._limiter = AsyncLimiter(max_rate=requests_per_second, time_period=1.0)

    async def fetch(self, short_id: str) -> bytes:
        if short_id not in EURLEX_CATALOG:
            raise ValueError(f"Atto UE sconosciuto: {short_id!r}")
        info = EURLEX_CATALOG[short_id]
        async with (
            httpx.AsyncClient(
                headers={
                    "User-Agent": self._user_agent,
                    "Accept-Language": "it-IT,it;q=0.9",
                },
                timeout=self._timeout,
                follow_redirects=True,
            ) as client,
            self._limiter,
        ):
            resp = await client.get(self.BASE, params={"uri": f"CELEX:{info.celex}"})
        resp.raise_for_status()
        content = resp.content
        if b"ti-art" not in content and b"Articolo" not in content:
            raise EurlexFetchError(
                f"Risposta EUR-Lex per {info.celex} senza marcatori articolo (login/errore?)"
            )
        logger.info("eurlex.fetched", celex=info.celex, size_bytes=len(content))
        return content


# ---------------------------------------------------------------------------
# Parser HTML → CanonicalAct
# ---------------------------------------------------------------------------

_ART_TITLE_RE = re.compile(r"^\s*Articolo\s+([0-9]+(?:\s*(?:bis|ter|quater|quinquies))?)\s*$", re.I)
_COMMA_NUM_RE = re.compile(r"^\s*([0-9]{1,3})\.\s+")


def _class_contains(el: lxml_html.HtmlElement, fragment: str) -> bool:
    return fragment in (el.get("class") or "")


class EurlexParser:
    """Parsa l'HTML EUR-Lex in CanonicalAct (solo articolato, no allegati)."""

    def parse_bytes(self, html_bytes: bytes, *, short_id: str) -> CanonicalAct:
        if short_id not in EURLEX_CATALOG:
            raise ValueError(f"Atto UE sconosciuto: {short_id!r}")
        info = EURLEX_CATALOG[short_id]
        doc = lxml_html.fromstring(html_bytes)

        articles = self._extract_articles(doc)
        logger.info("eurlex.parsed", short_id=short_id, articles=len(articles))
        if not articles:
            raise EurlexFetchError(f"Nessun articolo estratto da {info.celex}")

        root = CanonicalPartition(
            kind=NormPartitionKind.LIBRO,
            number="0",
            label=info.title,
            rubrica=None,
            full_text=None,
            commi=[],
            children=articles,
        )
        return CanonicalAct(
            urn=f"celex:{info.celex}",
            short_id=info.short_id,
            title=info.title,
            type=info.type,
            issued_at=info.issued_at,
            in_force_from=info.in_force_from,
            in_force_to=None,
            # Il testo scaricato è la versione GU (vedi docstring modulo):
            # usiamo la data dell'atto come expression date.
            expression_date=info.issued_at,
            source_url=f"https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:{info.celex}",
            source_hash=hashlib.sha256(html_bytes).hexdigest(),
            root=[root],
        )

    def _extract_articles(self, doc: lxml_html.HtmlElement) -> list[CanonicalPartition]:
        # Marcatori articolo: <p class="ti-art">Articolo 1</p> (o oj-ti-art,
        # o <div class="eli-title"> nelle versioni più nuove).
        markers: list[tuple[lxml_html.HtmlElement, str]] = []
        for el in doc.iter():
            if not isinstance(el.tag, str):  # commenti/PI
                continue
            cls = el.get("class") or ""
            if "ti-art" in cls and "sti" not in cls:
                text = " ".join(el.itertext()).strip()
                m = _ART_TITLE_RE.match(text)
                if m:
                    num = re.sub(r"\s+", "-", m.group(1).strip()).lower()
                    markers.append((el, num))

        # Fallback per il formato pre-2010 (nessuna class): <p>Articolo N</p>
        # come unico contenuto dell'elemento.
        if not markers:
            for el in doc.iter("p"):
                if not isinstance(el.tag, str):
                    continue
                text = " ".join(el.itertext()).strip()
                m = _ART_TITLE_RE.match(text)
                if m:
                    num = re.sub(r"\s+", "-", m.group(1).strip()).lower()
                    markers.append((el, num))

        articles: list[CanonicalPartition] = []
        for i, (el, num) in enumerate(markers):
            next_el = markers[i + 1][0] if i + 1 < len(markers) else None
            rubrica, body_text = self._collect_article_body(el, next_el)
            commi = self._split_commi(body_text)
            full_text = body_text.strip()
            if rubrica:
                full_text = f"[Rubrica] {rubrica}\n\n{full_text}"
            if not full_text.strip():
                continue
            articles.append(
                CanonicalPartition(
                    kind=NormPartitionKind.ARTICOLO,
                    number=num,
                    label=f"art. {num}",
                    rubrica=rubrica,
                    full_text=full_text,
                    commi=commi,
                )
            )
        return articles

    def _collect_article_body(
        self,
        marker: lxml_html.HtmlElement,
        next_marker: lxml_html.HtmlElement | None,
    ) -> tuple[str | None, str]:
        """Raccoglie rubrica + corpo tra due marcatori di articolo."""
        rubrica: str | None = None
        parts: list[str] = []
        el = marker
        while True:
            el = el.getnext()
            if el is None or (next_marker is not None and el is next_marker):
                break
            if not isinstance(el.tag, str):  # commenti/PI
                continue
            cls = el.get("class") or ""
            text = " ".join(t.strip() for t in el.itertext() if t.strip())
            text = text.replace("\xa0", " ")
            text = re.sub(r"[ \t]+", " ", text).strip()
            if not text:
                continue
            # Stop su titoli di capo/sezione/allegato che separano gli articoli
            if any(k in cls for k in ("ti-section", "ti-grseq", "doc-ti", "annex")):
                if next_marker is None:
                    break
                continue
            # Rubrica: <p class="sti-art"> (vecchio formato) oppure
            # <div class="eli-title"> (formato eli, GDPR e successivi).
            if rubrica is None and ("sti-art" in cls or "eli-title" in cls):
                rubrica = text
                continue
            parts.append(text)
        return rubrica, "\n".join(parts)

    @staticmethod
    def _split_commi(body: str) -> list[CanonicalComma]:
        """Divide in paragrafi numerati ("1.   ..."); fallback: comma unico."""
        lines = [line for line in body.split("\n") if line.strip()]
        commi: list[CanonicalComma] = []
        current_num: str | None = None
        current: list[str] = []

        def flush() -> None:
            if current:
                commi.append(
                    CanonicalComma(
                        number=current_num or str(len(commi) + 1),
                        text=" ".join(current).strip(),
                    )
                )

        for line in lines:
            m = _COMMA_NUM_RE.match(line)
            if m:
                flush()
                current = [line[m.end() :].strip()]
                current_num = m.group(1)
            else:
                current.append(line.strip())
        flush()

        if not commi and body.strip():
            return [CanonicalComma(number="1", text=body.strip())]
        return commi
