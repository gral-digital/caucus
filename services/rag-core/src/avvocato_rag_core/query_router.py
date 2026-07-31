"""Routing intento query → filtri corpus, hint retrieval, lookup articolo diretto.

Migliora scenari fattuali (etilometro → CDS) e query con riferimenti espliciti
(art. 575 c.p.) senza dipendere da un LLM di routing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from avvocato_rag_core.schemas.retrieval import RetrievalQuery

# art. 575 c.p. / articolo 2043 c.c. / art 186 cds
_ARTICLE_RE = re.compile(
    r"\bart(?:icolo)?\.?\s*"
    r"(\d+(?:\s*[-]?\s*(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?)"
    r"(?:\s*,?\s*(?:comma|co\.?|c\.?)\s*(\d+(?:\s*[-]?\s*(?:bis|ter))?))?"
    r"\s+"
    r"(c\.?\s*c\.?|c\.?\s*p\.?|c\.?\s*p\.?\s*c\.?|c\.?\s*p\.?\s*p\.?|"
    r"cod\.?\s*strada|cds|cdc|cost\.?|cpc|cpp|cad|ccii|ccp|"
    r"tu\s*stup\.?|tuir|stat\.?|l\.?\s*241|"
    # Forme lunghe (query utente in linguaggio naturale + output della query
    # expansion LLM, che scrive "art. 612-bis codice penale")
    r"(?:del\s+|della\s+)?codice\s+civile|(?:del\s+)?codice\s+penale|"
    r"(?:del\s+)?codice\s+di\s+procedura\s+civile|"
    r"(?:del\s+)?codice\s+di\s+procedura\s+penale|"
    r"(?:della\s+)?costituzione|(?:del\s+)?codice\s+della\s+strada|"
    r"(?:del\s+)?codice\s+del\s+consumo|(?:del\s+)?codice\s+del\s+turismo|"
    r"(?:del\s+)?gdpr|(?:dello\s+)?statuto\s+dei\s+lavoratori|"
    r"(?:del\s+)?d\.?\s*lgs\.?\s*(?:n\.?\s*)?231\s*/\s*2001|"
    r"(?:del\s+)?testo\s+unico\s+(?:sull[ae]\s+|dell[ae]\s+)?"
    r"(?:immigrazione|edilizia|bancario|finanza|ambiente|sicurezza\s+sul\s+lavoro))",
    re.IGNORECASE,
)

_SUFFIX_TO_SHORT: dict[str, str] = {
    "cc": "cc",
    "c.c": "cc",
    "c. c": "cc",
    "cp": "cp",
    "c.p": "cp",
    "c. p": "cp",
    "cpc": "cpc",
    "c.p.c": "cpc",
    "cpp": "cpp",
    "c.p.p": "cpp",
    "cds": "cds",
    "cod. strada": "cds",
    "cod strada": "cds",
    "cdc": "cdc",
    "cost": "cost",
    "cad": "cad",
    "ccii": "ccii",
    "ccp": "ccp",
    "tuir": "tuir",
    "stat": "stat",
    "l. 241": "l241",
    "l 241": "l241",
    # Forme lunghe (normalizzate: minuscole, senza punti né spazi)
    "codicecivile": "cc",
    "delcodicecivile": "cc",
    "dellacodicecivile": "cc",
    "codicepenale": "cp",
    "delcodicepenale": "cp",
    "codicediproceduracivile": "cpc",
    "delcodicediproceduracivile": "cpc",
    "codicediprocedurapenale": "cpp",
    "delcodicediprocedurapenale": "cpp",
    "costituzione": "cost",
    "dellacostituzione": "cost",
    "codicedellastrada": "cds",
    "delcodicedellastrada": "cds",
    "codicedelconsumo": "cdc",
    "delcodicedelconsumo": "cdc",
    "gdpr": "gdpr",
    "delgdpr": "gdpr",
    "statutodeilavoratori": "stat",
    "dellostatutodeilavoratori": "stat",
    "dlgs231/2001": "dlgs231",
    "deldlgs231/2001": "dlgs231",
    "dlgsn231/2001": "dlgs231",
    "testounicosullimmigrazione": "tui",
    "testounicodellimmigrazione": "tui",
    "deltestounicosullimmigrazione": "tui",
    "testounicodelledilizia": "tue",
    "deltestounicodelledilizia": "tue",
    "testounicobancario": "tub",
    "deltestounicobancario": "tub",
    "testounicodellafinanza": "tuf",
    "deltestounicodellafinanza": "tuf",
    "testounicodellambiente": "tua",
    "deltestounicodellambiente": "tua",
    "testounicosullasicurezzasullavoro": "tusl",
    "deltestounicosullasicurezzasullavoro": "tusl",
}


def _normalize_suffix(raw: str) -> str | None:
    s = re.sub(r"\s+", " ", raw.lower().strip())
    compact = s.replace(".", "").replace(" ", "")
    if compact in _SUFFIX_TO_SHORT:
        return _SUFFIX_TO_SHORT[compact]
    return _SUFFIX_TO_SHORT.get(s)


def _normalize_art_num(raw: str) -> str:
    return re.sub(r"\s+", "-", raw.strip()).lower()


@dataclass(frozen=True, slots=True)
class ArticleRef:
    source: str
    num: str


@dataclass(frozen=True, slots=True)
class MatterRule:
    keywords: tuple[str, ...]
    sources: tuple[str, ...]
    fts_terms: tuple[str, ...]
    intent: str
    direct_articles: tuple[ArticleRef, ...] = ()


# Regole materia: keyword → source preferite, termini FTS, lookup diretto articoli chiave
_MATTER_RULES: tuple[MatterRule, ...] = (
    MatterRule(
        ("etilometro", "alcool", "alcolem", "ebbrezza", "guida", "guidare", "g/l", "guidato"),
        ("cds",),
        ("guida", "ebbrezza", "alcool", "etilometro", "186"),
        "traffic",
        (ArticleRef("cds", "186"),),
    ),
    MatterRule(
        ("omicidio", "uccisione"),
        ("cp",),
        ("omicidio", "575"),
        "homicide",
        (ArticleRef("cp", "575"),),
    ),
    MatterRule(
        ("dolo", "colpa"),
        ("cp",),
        ("dolo", "colpa", "42", "43"),
        "mens_rea",
        (ArticleRef("cp", "42"), ArticleRef("cp", "43")),
    ),
    MatterRule(
        ("furto", "sottrazione", "rubare"),
        ("cp",),
        ("furto", "624"),
        "theft",
        (ArticleRef("cp", "624"),),
    ),
    MatterRule(
        ("truffa", "artifizi", "raggiro"),
        ("cp",),
        ("truffa", "640", "artifizi"),
        "fraud",
        (ArticleRef("cp", "640"),),
    ),
    MatterRule(
        ("legittima difesa", "difesa personale"),
        ("cp",),
        ("legittima difesa", "52"),
        "self_defense",
        (ArticleRef("cp", "52"),),
    ),
    MatterRule(
        ("risarcimento", "fatto illecito", "danno extracontrattuale"),
        ("cc",),
        ("risarcimento", "2043", "fatto illecito"),
        "tort",
        (ArticleRef("cc", "2043"),),
    ),
    MatterRule(
        ("contratto", "inadempimento", "obbligazione"),
        ("cc",),
        ("inadempimento", "1218", "contratto"),
        "contract",
        (ArticleRef("cc", "1218"),),
    ),
    MatterRule(
        ("prescrizione", "termine prescrizionale"),
        ("cc",),
        ("prescrizione", "2946", "dieci anni"),
        "prescription",
        (ArticleRef("cc", "2946"),),
    ),
    MatterRule(
        ("annull", "vizio", "errore", "dolo"),
        ("cc",),
        ("annullamento", "contratto", "1427", "1439", "errore", "dolo"),
        "contract_void",
        (ArticleRef("cc", "1427"), ArticleRef("cc", "1439"), ArticleRef("cc", "1438")),
    ),
    MatterRule(
        ("licenziamento", "lavoro", "datore"),
        ("stat", "cc"),
        ("licenziamento", "2119", "statuto"),
        "labor",
    ),
    MatterRule(
        ("reato tentato", "tentativo"),
        ("cp",),
        ("tentato", "56"),
        "attempt",
        (ArticleRef("cp", "56"),),
    ),
    MatterRule(
        ("violenza privata",),
        ("cp",),
        ("violenza privata", "610"),
        "coercion",
        (ArticleRef("cp", "610"),),
    ),
    MatterRule(
        ("custod", "cosa in custodia"),
        ("cc",),
        ("custodia", "2051"),
        "custody",
        (ArticleRef("cc", "2051"),),
    ),
)


@dataclass(frozen=True, slots=True)
class RoutedQuery:
    """Query arricchita per retrieval multi-stage."""

    original_text: str
    retrieval_text: str
    sources: list[str] | None = None
    direct_articles: tuple[ArticleRef, ...] = ()
    fts_extra_terms: tuple[str, ...] = ()
    intent: str = "general"
    hints: tuple[str, ...] = ()


def route_query(text: str, *, base_sources: list[str] | None = None) -> RoutedQuery:
    """Analizza la domanda e produce hint per vector + FTS + lookup diretto."""
    q = text.strip()
    q_lower = q.lower()

    direct: list[ArticleRef] = []
    for m in _ARTICLE_RE.finditer(q):
        suffix = _normalize_suffix(m.group(3))
        if suffix:
            direct.append(ArticleRef(source=suffix, num=_normalize_art_num(m.group(1))))

    sources: list[str] = list(base_sources) if base_sources else []
    fts_terms: list[str] = []
    hints: list[str] = []
    intent = "general"
    retrieval_extra: list[str] = []
    matched_rules: list[MatterRule] = []

    for rule in _MATTER_RULES:
        if not _rule_matches(q_lower, rule):
            continue
        matched_rules.append(rule)
        intent = rule.intent
        for s in rule.sources:
            if s not in sources:
                sources.append(s)
        fts_terms.extend(rule.fts_terms)
        for ref in rule.direct_articles:
            if ref not in direct:
                direct.append(ref)
        hints.append(rule.intent)

    # Omicidio volontario vs colposo: disambiguazione esplicita
    if "omicidio" in q_lower and any(w in q_lower for w in ("volontario", "volontaria", "dolo")):
        if not any(a.num == "575" for a in direct):
            direct.append(ArticleRef(source="cp", num="575"))
        fts_terms.extend(["omicidio", "575"])
        retrieval_extra.append("omicidio art 575")
    elif "omicidio" in q_lower and "colposo" in q_lower:
        fts_terms.extend(["omicidio colposo", "589"])
        retrieval_extra.append("omicidio colposo art 589")

    # Scenario etilometro: enfatizza norma sostanziale, non solo difesa processuale
    if intent == "traffic":
        if not any(a.source == "cds" and a.num == "186" for a in direct):
            direct.append(ArticleRef(source="cds", num="186"))
        retrieval_extra.extend(["guida stato ebbrezza alcool art 186 codice strada"])

    retrieval_text = q
    if retrieval_extra:
        retrieval_text = f"{q}\n\n" + " ".join(retrieval_extra)

    return RoutedQuery(
        original_text=q,
        retrieval_text=retrieval_text,
        sources=sources or None,
        direct_articles=tuple(direct),
        fts_extra_terms=tuple(dict.fromkeys(fts_terms)),
        intent=intent,
        hints=tuple(hints),
    )


def _rule_matches(q_lower: str, rule: MatterRule) -> bool:
    """Per regole multi-keyword (dolo+colpa) richiede tutte; altrimenti any."""
    if rule.intent == "mens_rea":
        return "dolo" in q_lower and "colpa" in q_lower
    if rule.intent == "contract_void":
        return any(k in q_lower for k in ("annull", "vizio", "errore")) and "contratt" in q_lower
    if rule.intent == "contract":
        if "annull" in q_lower or "vizio" in q_lower:
            return False
        return any(kw in q_lower for kw in rule.keywords)
    if rule.intent == "attempt":
        return "tentat" in q_lower
    return any(kw in q_lower for kw in rule.keywords)


def apply_routing(query: RetrievalQuery, routed: RoutedQuery) -> RetrievalQuery:
    """Applica routing a una RetrievalQuery esistente (merge sources)."""
    merged_sources = list(query.sources or [])
    if routed.sources:
        for s in routed.sources:
            if s not in merged_sources:
                merged_sources.append(s)

    return query.model_copy(
        update={
            "text": routed.retrieval_text,
            "sources": merged_sources or None,
        }
    )
