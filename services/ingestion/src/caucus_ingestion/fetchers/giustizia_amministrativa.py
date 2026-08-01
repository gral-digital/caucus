"""Fetcher per il portale della Giustizia Amministrativa (TAR + Consiglio di Stato).

Il portale espone pubblicamente (senza autenticazione) la ricerca «Decisioni
e pareri» come portlet Liferay:

    GET  https://www.giustizia-amministrativa.it/web/guest/dcsnprr
         → pagina col form; da qui si estraggono l'instance id del portlet e
           il token ``p_auth`` (cambiano nel tempo: MAI hardcodarli)
    POST /web/guest/dcsnprr?p_p_id=...&p_p_lifecycle=1&..._javax.portlet.action=search&p_auth=...
         → pagina HTML coi risultati (metadati + link al testo integrale)

I testi integrali sono su ``mdp.giustizia-amministrativa.it/visualizza/`` in
HTML (alcuni provvedimenti storici solo PDF: v1 li scarta contandoli). Gli
oscuramenti ex art. 52 cod. privacy sono applicati a monte dal portale.

Note d'uso verificate (2026-07-31): nessun robots.txt, nessuna clausola di
divieto di riuso nelle note del sito; provvedimenti soggetti a pubblicità
legale. Postura identica a SentenzeWeb: rate limit conservativo, User-Agent
identificato, pagine piccole.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass

import httpx
import structlog
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# Il visualizzatore mdp serve documenti XML-ish: il parser lxml-html li
# gestisce correttamente, il warning è solo rumore.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = structlog.get_logger(__name__)

_BASE = "https://www.giustizia-amministrativa.it"
_SEARCH_PAGE = f"{_BASE}/web/guest/dcsnprr"

# ECLI dei provvedimenti amministrativi: ECLI:IT:TARLAZ:2026:13993SENT
_ECLI_RE = re.compile(r"ECLI:IT:[A-Z0-9]+:\d{4}:\d+[A-Z]+")
_PORTLET_ID_RE = re.compile(r"decisioni_pareri_web_DecisioniPareriWebPortlet_INSTANCE_(\w+)")
_P_AUTH_RE = re.compile(r"p_auth=(\w+)")


@dataclass(frozen=True, slots=True)
class GAProvvedimento:
    """Un provvedimento come appare nei risultati di ricerca."""

    external_id: str  # ECLI se presente, altrimenti schema:numeroprovv
    tipo: str  # SENTENZA | ORDINANZA | DECRETO | PARERE
    sede: str  # "ROMA", "CONSIGLIO DI STATO", …
    sezione: str | None
    numero: str  # numero provvedimento (es. "202613993")
    anno: int
    nrg: str | None  # numero di registro generale del ricorso
    ecli: str | None
    doc_url: str  # testo integrale su mdp.giustizia-amministrativa.it


@dataclass(frozen=True, slots=True)
class _PortletContext:
    instance_id: str
    p_auth: str


def _parse_results(html: str) -> list[GAProvvedimento]:
    """Estrae i provvedimenti dalla pagina risultati del portlet."""
    soup = BeautifulSoup(html, "lxml")
    out: list[GAProvvedimento] = []
    # Ogni risultato ha un link al visualizzatore mdp; il blocco di testo
    # attorno contiene tipo/sede/sezione/numero/nrg/ECLI.
    seen: set[str] = set()
    for a in soup.find_all("a", href=re.compile(r"mdp\.giustizia-amministrativa\.it/visualizza")):
        href = str(a.get("href") or "")
        if not href or href in seen or ".pdf" in href.lower():
            # v1: solo testi HTML (i PDF storici richiedono estrazione a parte)
            if href:
                seen.add(href)
            continue
        seen.add(href)
        block = a.find_parent("div")
        for _ in range(3):
            if block is not None and len(block.get_text(strip=True)) > 80:
                break
            block = block.find_parent("div") if block is not None else None
        text = block.get_text(" ", strip=True) if block is not None else ""

        m_num = re.search(r"numero provv\.?:?\s*(\d+)", text, re.I)
        m_sede = re.search(r"sede di\s+([A-ZÀ-Ù' .]+?)\s*,", text, re.I)
        m_sez = re.search(r"sezione\s+([A-Z0-9 ]+?)\s*,", text, re.I)
        m_nrg = re.search(r"Numero ricorso:?\s*(\d+)", text, re.I)
        m_ecli = _ECLI_RE.search(text)
        m_tipo = re.search(r"\b(SENTENZA|ORDINANZA|DECRETO|PARERE)\b", text)

        numero = m_num.group(1) if m_num else ""
        if not numero:
            m_file = re.search(r"nomeFile=(\d+)_", href)
            numero = m_file.group(1) if m_file else ""
        if not numero:
            continue
        anno = int(numero[:4]) if len(numero) >= 8 and numero[:4].isdigit() else 0
        ecli = m_ecli.group(0) if m_ecli else None
        schema = re.search(r"schema=([a-z_]+)", href)
        external_id = ecli or f"{schema.group(1) if schema else 'ga'}:{numero}"
        out.append(
            GAProvvedimento(
                external_id=external_id,
                tipo=(m_tipo.group(1) if m_tipo else "SENTENZA").upper(),
                sede=(m_sede.group(1).strip() if m_sede else "").upper() or "N/D",
                sezione=m_sez.group(1).strip() if m_sez else None,
                numero=numero,
                anno=anno,
                nrg=m_nrg.group(1) if m_nrg else None,
                ecli=ecli,
                doc_url=href,
            )
        )
    return out


# L'inizio vero del provvedimento: tutto ciò che precede è cornice del
# visualizzatore o metadati interni del gestionale (nomi file, percorsi di
# rete, operatori) che NON devono finire nel corpus.
_DOC_START_MARKERS = (
    "REPUBBLICA ITALIANA",
    "Il Consiglio di Stato",
    "Il Tribunale Amministrativo",
    "Il Consiglio di Giustizia",
)


def _extract_document_text(html: str) -> str | None:
    """Testo del provvedimento dalla pagina del visualizzatore mdp."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    starts = [i for m in _DOC_START_MARKERS if (i := text.find(m)) >= 0]
    if not starts:
        return None  # niente marcatore = probabile pagina errore/PDF: scarta
    text = text[min(starts) :]
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text if len(text) >= 500 else None


class GiustiziaAmministrativaFetcher:
    """Ricerca e download dei provvedimenti della giustizia amministrativa."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 60.0,
        requests_per_second: float = 0.5,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        self._limiter = AsyncLimiter(max_rate=1, time_period=1.0 / requests_per_second)
        self._client: httpx.AsyncClient | None = None
        self._ctx: _PortletContext | None = None

    async def __aenter__(self) -> GiustiziaAmministrativaFetcher:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self._user_agent},
            timeout=self._timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _portlet_context(self) -> _PortletContext:
        """Instance id + p_auth dalla pagina del form (mai hardcodati)."""
        if self._ctx is not None:
            return self._ctx
        assert self._client is not None
        async with self._limiter:
            resp = await self._client.get(_SEARCH_PAGE)
        resp.raise_for_status()
        m_id = _PORTLET_ID_RE.search(resp.text)
        m_auth = _P_AUTH_RE.search(resp.text)
        if not m_id or not m_auth:
            raise RuntimeError(
                "layout del portale cambiato: instance id o p_auth non trovati "
                "nella pagina di ricerca (aggiornare il fetcher)"
            )
        self._ctx = _PortletContext(instance_id=m_id.group(1), p_auth=m_auth.group(1))
        logger.info("ga.portlet_context", instance_id=self._ctx.instance_id)
        return self._ctx

    async def search(
        self,
        *,
        sede: str,
        anno: int,
        tipo: str = "Sentenza",
        page: int = 1,
        page_size: int = 60,
    ) -> list[GAProvvedimento]:
        """Una pagina di risultati per (sede, anno, tipo).

        ``sede``: "Consiglio di Stato" o nome città TAR (come nel form).
        """
        assert self._client is not None
        ctx = await self._portlet_context()
        prefix = f"_decisioni_pareri_web_DecisioniPareriWebPortlet_INSTANCE_{ctx.instance_id}_"
        params = {
            "p_p_id": f"decisioni_pareri_web_DecisioniPareriWebPortlet_INSTANCE_{ctx.instance_id}",
            "p_p_lifecycle": "1",
            "p_p_state": "normal",
            "p_p_mode": "view",
            f"{prefix}javax.portlet.action": "search",
            "p_auth": ctx.p_auth,
        }
        data = {
            f"{prefix}searchtextProvvedimenti": "",
            f"{prefix}pageSize": str(page_size),
            f"{prefix}TipoProvvedimentoItem": tipo,
            f"{prefix}sedeProvvedimenti": sede,
            # I value delle option coincidono con le label ("Consiglio di
            # Stato", nomi città, "Sentenza"): verificato sull'HTML del form.
            f"{prefix}DataYearItem": str(anno),
            f"{prefix}numeroProvvedimenti": "",
            f"{prefix}isAdvancedSearch": "false",
            f"{prefix}step": str(page),
            f"{prefix}cur": str(page),
        }
        async with self._limiter:
            resp = await self._client.post(_SEARCH_PAGE, params=params, data=data)
        resp.raise_for_status()
        docs = _parse_results(resp.text)
        logger.info("ga.search_page", sede=sede, anno=anno, tipo=tipo, page=page, found=len(docs))
        return docs

    async def fetch_text(self, doc: GAProvvedimento) -> str | None:
        """Testo integrale del provvedimento (None per PDF/pagine vuote)."""
        assert self._client is not None
        async with self._limiter:
            resp = await self._client.get(doc.doc_url)
        if resp.status_code != 200:
            logger.warning("ga.fetch_failed", url=doc.doc_url, status=resp.status_code)
            return None
        return _extract_document_text(resp.text)
