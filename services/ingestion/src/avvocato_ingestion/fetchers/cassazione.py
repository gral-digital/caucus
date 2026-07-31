"""Fetcher per SentenzeWeb (Corte di Cassazione, italgiure.giustizia.it).

SentenzeWeb espone pubblicamente (senza autenticazione) un proxy Solr:

    POST https://www.italgiure.giustizia.it/sncass/isapi/hc.dll/sn.solr/sn-collection/select?app.query
    body x-www-form-urlencoded: q=(kind:"snpen"), rows=N, start=M, wt=json, sort=...

I documenti contengono il testo integrale ANONIMIZZATO della sentenza (campo
``ocr``), il dispositivo (``ocrdis``), gli estremi (sezione, numero, anno,
date, presidente, relatore) e i riferimenti normativi codificati (``rnc-*``).

Il servizio è offerto "per la libera consultazione da parte del cittadino":
manteniamo un rate limit conservativo (default 0.5 req/s) e pagine piccole.
Le sentenze appena depositate possono essere "in fase di oscuramento"
(anonimizzazione in corso): vengono scartate e riprese all'harvest successivo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
import structlog
import truststore
from aiolimiter import AsyncLimiter

logger = structlog.get_logger(__name__)

_BASE = "https://www.italgiure.giustizia.it/sncass"
_SELECT = f"{_BASE}/isapi/hc.dll/sn.solr/sn-collection/select?app.query"

# Testi placeholder per sentenze non ancora anonimizzate.
_OSCURAMENTO_MARKERS = ("fase di oscuramento", "in corso di oscuramento")


@dataclass(frozen=True, slots=True)
class SentenzaDoc:
    """Documento normalizzato da SentenzeWeb."""

    external_id: str
    kind: str  # snciv | snpen
    tipoprov: str | None
    sezione: str | None
    numero: str
    anno: int
    ecli: str | None
    data_decisione: date | None
    data_deposito: date | None
    presidente: str | None
    relatore: str | None
    materia: str | None
    dispositivo: str | None
    full_text: str
    filename: str | None
    riferimenti: list[str]


def _first(v: Any) -> Any:
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _parse_yyyymmdd(v: Any) -> date | None:
    s = str(_first(v) or "")
    if len(s) == 8 and s.isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    return None


def _normalize_doc(raw: dict[str, Any]) -> SentenzaDoc | None:
    text = " ".join(raw.get("ocr") or []).strip()
    if not text or len(text) < 500:
        return None
    lowered = text.lower()
    if any(m in lowered for m in _OSCURAMENTO_MARKERS):
        return None
    external_id = str(raw.get("id") or "")
    kind = str(raw.get("kind") or "")
    numero = str(raw.get("numdec") or "")
    anno_raw = str(raw.get("anno") or "0")
    if not external_id or kind not in ("snciv", "snpen") or not numero:
        return None
    # Riferimenti normativi codificati: li conserviamo grezzi nel metadata
    # (gen = fonte, art = articolo) per un futuro linking al grafo.
    refs = []
    gens = raw.get("rnc-gen") or []
    arts = raw.get("rnc-art") or []
    for g, a in zip(gens, arts, strict=False):
        refs.append(f"{g}:{str(a).strip()}")
    return SentenzaDoc(
        external_id=external_id,
        kind=kind,
        tipoprov=_first(raw.get("tipoprov")),
        sezione=str(_first(raw.get("szdec")) or "") or None,
        numero=numero,
        anno=int(anno_raw) if anno_raw.isdigit() else 0,
        ecli=_first(raw.get("ecli")),
        data_decisione=_parse_yyyymmdd(raw.get("datdec")),
        data_deposito=_parse_yyyymmdd(raw.get("datdep")),
        presidente=_first(raw.get("presidente")),
        relatore=_first(raw.get("relatore")),
        materia=_first(raw.get("materia")),
        dispositivo=" ".join(raw.get("ocrdis") or []).strip() or None,
        full_text=text,
        filename=_first(raw.get("filename")),
        riferimenti=refs[:64],
    )


class SentenzeWebFetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 60.0,
        requests_per_second: float = 0.5,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        # 1 acquisizione ogni 1/rps secondi (AsyncLimiter richiede max_rate >= 1)
        self._limiter = AsyncLimiter(max_rate=1, time_period=1.0 / requests_per_second)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> SentenzeWebFetcher:
        # italgiure serve una catena TLS incompleta per certifi: usiamo il
        # trust store di sistema (stessa verifica di curl/browser), NON
        # disabilitiamo la verifica.
        import ssl

        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": self._user_agent,
                "Referer": f"{_BASE}/",
            },
            timeout=self._timeout,
            verify=ctx,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def search(
        self,
        *,
        kind: str,
        start: int = 0,
        rows: int = 50,
        query_extra: str | None = None,
    ) -> tuple[int, list[SentenzaDoc], int]:
        """Una pagina di risultati, più recenti prima.

        Ritorna (num_found_totale, documenti validi, documenti grezzi ricevuti).
        """
        assert self._client is not None, "usare come async context manager"
        q = f'(kind:"{kind}")'
        if query_extra:
            q = f"({q} AND {query_extra})"
        async with self._limiter:
            resp = await self._client.post(
                _SELECT,
                data={
                    "q": q,
                    "rows": str(rows),
                    "start": str(start),
                    "wt": "json",
                    "sort": "pd desc,numdec desc",
                },
            )
        resp.raise_for_status()
        payload = resp.json()
        response = payload.get("response") or {}
        raw_docs = response.get("docs") or []
        docs = [d for d in (_normalize_doc(r) for r in raw_docs) if d is not None]
        num_found = int(response.get("numFound") or 0)
        logger.info(
            "sentenzeweb.page",
            kind=kind,
            start=start,
            received=len(raw_docs),
            valid=len(docs),
            num_found=num_found,
        )
        return num_found, docs, len(raw_docs)
