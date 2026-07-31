"""Registro estremi ufficiali → short_id delle fonti indicizzate.

La query expansion LLM (e gli utenti esperti) citano gli atti per estremi
ufficiali — "art. 17 D.Lgs. 81/2008", "art. 5 L. 300/1970" — non con le sigle
interne. Questo registro permette al query router di risolverli in short_id.

Generato dagli URN di CODICI_CATALOG (services/ingestion); mantenere allineato
quando si aggiungono fonti (il test test_query_router lo verifica a campione).
Chiave: (tipo, numero, anno) con tipo in {"dlgs", "l", "dpr", "rd"}.
"""

from __future__ import annotations

ACT_REFS: dict[tuple[str, str, str], str] = {
    ("dlgs", "104", "2010"): "cpa",
    ("dlgs", "117", "2017"): "cts",
    ("dlgs", "14", "2019"): "ccii",
    ("dlgs", "151", "2001"): "tumat",
    ("dlgs", "152", "2006"): "tua",
    ("dlgs", "159", "2011"): "cam",
    ("dlgs", "165", "2001"): "tupi",
    ("dlgs", "196", "2003"): "cpriv",
    ("dlgs", "206", "2005"): "cdc",
    ("dlgs", "209", "2005"): "cap",
    ("dlgs", "23", "2015"): "dlgs23",
    ("dlgs", "231", "2001"): "dlgs231",
    ("dlgs", "231", "2002"): "ritpag",
    ("dlgs", "231", "2007"): "aml",
    ("dlgs", "24", "2023"): "wb",
    ("dlgs", "267", "2000"): "tuel",
    ("dlgs", "285", "1992"): "cds",
    ("dlgs", "286", "1998"): "tui",
    ("dlgs", "33", "2013"): "dlgs33",
    ("dlgs", "36", "2023"): "ccp",
    ("dlgs", "385", "1993"): "tub",
    ("dlgs", "39", "2013"): "dlgs39",
    ("dlgs", "42", "2004"): "cbc",
    ("dlgs", "546", "1992"): "cpt",
    ("dlgs", "58", "1998"): "tuf",
    ("dlgs", "81", "2008"): "tusl",
    ("dlgs", "81", "2015"): "lav81",
    ("dlgs", "82", "2005"): "cad",
    ("dpr", "309", "1990"): "tus",
    ("dpr", "380", "2001"): "tue",
    ("dpr", "445", "2000"): "tudoc",
    ("dpr", "447", "1988"): "cpp",
    ("dpr", "600", "1973"): "dpr600",
    ("dpr", "633", "1972"): "iva",
    ("dpr", "917", "1986"): "tuir",
    ("l", "190", "2012"): "l190",
    ("l", "241", "1990"): "l241",
    ("l", "247", "2012"): "lpf",
    ("l", "300", "1970"): "stat",
    ("l", "392", "1978"): "l392",
    ("l", "604", "1966"): "l604",
    ("l", "689", "1981"): "l689",
    ("l", "76", "2016"): "l76",
    ("l", "898", "1970"): "l898",
    ("l", "91", "1992"): "l91",
    ("rd", "1398", "1930"): "cp",
    ("rd", "1443", "1940"): "cpc",
    ("rd", "262", "1942"): "cc",
    ("rd", "327", "1942"): "cnav",
}


def resolve_act_ref(tipo: str, numero: str, anno: str) -> str | None:
    """Risolve estremi ufficiali in short_id. Anno a 2 cifre: 19xx se > 30."""
    if len(anno) == 2:
        anno = ("19" if int(anno) > 30 else "20") + anno
    return ACT_REFS.get((tipo, numero, anno))
