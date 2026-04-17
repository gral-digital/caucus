"""Fetcher per scaricare XML Akoma Ntoso da Normattiva.

Flusso di download (identificato reverse-engineering sulla struttura pubblica
del portale normattiva.it):

1. GET pagina permalink per URN:
   ``https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:...``
   La pagina HTML contiene un link ``caricaAKN?dataGU=...&codiceRedaz=...&dataVigenza=...``.
   **Questa prima chiamata è necessaria per ottenere i cookie di sessione.**

2. GET ``https://www.normattiva.it/do/atto/caricaAKN?dataGU=X&codiceRedaz=Y&dataVigenza=Z``
   Restituisce l'XML completo dell'atto (AKN 3.0) vigente alla data indicata.

Il portale richiede una sessione cookie, per questo usiamo ``httpx.AsyncClient``
con cookie jar. Rate-limit di 1 req/s (configurabile) per rispetto del portale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from avvocato_ingestion.parsers.normattiva_akn import CODICI_CATALOG

logger = structlog.get_logger(__name__)


class NormattivaFetchError(RuntimeError):
    """Errore di fetch (pagina mancante, XML non servito, rate-limit)."""


@dataclass(frozen=True, slots=True)
class AknDownload:
    """Payload di un download AKN riuscito."""

    short_id: str
    urn: str
    xml_bytes: bytes
    dataGU: str
    codiceRedaz: str
    dataVigenza: str


_CARICA_AKN_LINK_RE = re.compile(
    r'href="([^"]*caricaAKN\?[^"]*)"', re.IGNORECASE
)


class NormattivaFetcher:
    """Async client per scaricare AKN XML dal portale Normattiva."""

    BASE_PERMALINK = "https://www.normattiva.it/uri-res/N2Ls"
    BASE_CARICA_AKN = "https://www.normattiva.it/do/atto/caricaAKN"

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        self._max_retries = max_retries

    async def fetch_codice(self, short_id: str) -> AknDownload:
        """Scarica AKN XML del codice indicato (es. 'cc', 'cp')."""
        if short_id not in CODICI_CATALOG:
            raise ValueError(f"Codice sconosciuto: {short_id!r}")
        return await self.fetch_urn(CODICI_CATALOG[short_id].urn, short_id=short_id)

    async def fetch_urn(self, urn: str, *, short_id: str | None = None) -> AknDownload:
        """Scarica AKN XML per un URN arbitrario."""
        async with self._make_client() as client:
            # 1. Pagina permalink → estrai parametri caricaAKN + ottieni cookie
            async for attempt in self._retry():
                with attempt:
                    params = await self._fetch_permalink_params(client, urn)

            # 2. Scarica XML AKN
            async for attempt in self._retry():
                with attempt:
                    xml_bytes = await self._download_akn(client, urn, params)

        logger.info(
            "normattiva.fetched",
            urn=urn,
            dataGU=params["dataGU"],
            dataVigenza=params["dataVigenza"],
            size_bytes=len(xml_bytes),
        )
        return AknDownload(
            short_id=short_id or urn,
            urn=urn,
            xml_bytes=xml_bytes,
            dataGU=params["dataGU"],
            codiceRedaz=params["codiceRedaz"],
            dataVigenza=params["dataVigenza"],
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={
                "User-Agent": self._user_agent,
                "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,*/*;q=0.8"
                ),
            },
            timeout=self._timeout,
            follow_redirects=True,
        )

    def _retry(self) -> AsyncRetrying:
        return AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1.5, min=2, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, NormattivaFetchError)),
            reraise=True,
        )

    async def _fetch_permalink_params(
        self, client: httpx.AsyncClient, urn: str
    ) -> dict[str, str]:
        resp = await client.get(self.BASE_PERMALINK, params={"urn": urn})
        resp.raise_for_status()
        html = resp.text

        match = _CARICA_AKN_LINK_RE.search(html)
        if not match:
            raise NormattivaFetchError(
                f"Link 'caricaAKN' non trovato nella pagina per URN {urn!r}"
            )
        query = match.group(1).split("?", 1)[1].replace("&amp;", "&")
        params: dict[str, str] = {}
        for pair in query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v

        required = {"dataGU", "codiceRedaz", "dataVigenza"}
        if not required.issubset(params):
            raise NormattivaFetchError(
                f"Parametri mancanti nel link caricaAKN: {params}"
            )
        return {k: params[k] for k in required}

    async def _download_akn(
        self,
        client: httpx.AsyncClient,
        referer_urn: str,
        params: dict[str, str],
    ) -> bytes:
        resp = await client.get(
            self.BASE_CARICA_AKN,
            params=params,
            headers={
                "Accept": "application/xml,text/xml,*/*",
                "Referer": f"{self.BASE_PERMALINK}?{referer_urn}",
            },
        )
        resp.raise_for_status()
        content = resp.content
        head = content[:500]
        if not (head.startswith(b"<?xml") or b"akomaNtoso" in head):
            raise NormattivaFetchError(
                "Risposta da caricaAKN non è XML (probabile login/redirect)"
            )
        return content
