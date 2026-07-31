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


# short_id → denominazione della fonte indicizzata. Allineato a norm_source
# nel DB (stessa fonte di verità di CODICI_CATALOG in services/ingestion).
# Usato dalla query expansion per proporre articoli candidati in formato
# "sigla numero" e per validarne il parsing.
SOURCE_CATALOG: dict[str, str] = {
    "aiact": "Regolamento sull'intelligenza artificiale (AI Act, Reg. UE 2024/1689)",
    "aml": "Antiriciclaggio (D.Lgs. 231/2007)",
    "amld": "IV Direttiva antiriciclaggio (Dir. UE 2015/849)",
    "cad": "Codice dell'Amministrazione Digitale (D.Lgs. 82/2005)",
    "cam": "Codice delle leggi antimafia (D.Lgs. 159/2011)",
    "cap": "Codice delle Assicurazioni Private (D.Lgs. 209/2005)",
    "cbc": "Codice dei Beni Culturali e del Paesaggio (D.Lgs. 42/2004)",
    "cc": "Codice Civile",
    "ccii": "Codice della Crisi d'Impresa e dell'Insolvenza (D.Lgs. 14/2019)",
    "ccp": "Codice dei Contratti Pubblici (D.Lgs. 36/2023)",
    "cdc": "Codice del Consumo (D.Lgs. 206/2005)",
    "cds": "Codice della Strada (D.Lgs. 285/1992)",
    "cnav": "Codice della Navigazione",
    "cost": "Costituzione della Repubblica Italiana",
    "cp": "Codice Penale",
    "cpa": "Codice del Processo Amministrativo (D.Lgs. 104/2010)",
    "cpc": "Codice di Procedura Civile",
    "cpp": "Codice di Procedura Penale",
    "cpriv": "Codice privacy (D.Lgs. 196/2003)",
    "cpt": "Processo Tributario (D.Lgs. 546/1992)",
    "cts": "Codice del Terzo Settore (D.Lgs. 117/2017)",
    "dircons": "Direttiva sui diritti dei consumatori (Dir. 2011/83/UE)",
    "dlgs23": "Contratto a tutele crescenti (D.Lgs. 23/2015)",
    "dlgs231": "Responsabilità amministrativa degli enti (D.Lgs. 231/2001)",
    "dlgs33": "Trasparenza della pubblica amministrazione (D.Lgs. 33/2013)",
    "dlgs39": "Inconferibilità e incompatibilità di incarichi (D.Lgs. 39/2013)",
    "dma": "Regolamento sui mercati digitali (DMA, Reg. UE 2022/1925)",
    "dora": "Regolamento DORA (Reg. UE 2022/2554)",
    "dpr600": "Accertamento delle imposte sui redditi (D.P.R. 600/1973)",
    "dsa": "Regolamento sui servizi digitali (DSA, Reg. UE 2022/2065)",
    "eidas": "Regolamento eIDAS (Reg. UE 910/2014)",
    "eprivacy": "Direttiva ePrivacy (Dir. 2002/58/CE)",
    "gdpr": "Regolamento generale sulla protezione dei dati (GDPR)",
    "iva": "Disciplina dell'IVA (D.P.R. 633/1972)",
    "l190": "Prevenzione e repressione della corruzione (L. 190/2012)",
    "l241": "Procedimento amministrativo (L. 241/1990)",
    "l392": "Locazioni di immobili urbani (L. 392/1978)",
    "l604": "Licenziamenti individuali (L. 604/1966)",
    "l689": "Modifiche al sistema penale — depenalizzazione (L. 689/1981)",
    "l76": "Unioni civili e convivenze (L. 76/2016)",
    "l898": "Disciplina dei casi di scioglimento del matrimonio (L. 898/1970)",
    "l91": "Cittadinanza italiana (L. 91/1992)",
    "lav81": "Disciplina organica dei contratti di lavoro (D.Lgs. 81/2015)",
    "lpf": "Ordinamento della professione forense (L. 247/2012)",
    "mica": "Regolamento MiCA (Reg. UE 2023/1114)",
    "mifid2": "Direttiva MiFID II (Dir. 2014/65/UE)",
    "nis2": "Direttiva NIS2 (Dir. UE 2022/2555)",
    "psd2": "Direttiva PSD2 (Dir. UE 2015/2366)",
    "ritpag": "Ritardi di pagamento nelle transazioni commerciali (D.Lgs. 231/2002)",
    "stat": "Statuto dei Lavoratori (L. 300/1970)",
    "tua": "Testo Unico Ambiente (D.Lgs. 152/2006)",
    "tub": "Testo Unico Bancario (D.Lgs. 385/1993)",
    "tudoc": "Testo Unico Documentazione Amministrativa (D.P.R. 445/2000)",
    "tue": "Testo Unico dell'Edilizia (D.P.R. 380/2001)",
    "tuel": "Testo Unico Enti Locali (D.Lgs. 267/2000)",
    "tuf": "Testo Unico della Finanza (D.Lgs. 58/1998)",
    "tui": "Testo Unico Immigrazione (D.Lgs. 286/1998)",
    "tuir": "Testo Unico delle Imposte sui Redditi (D.P.R. 917/1986)",
    "tumat": "Testo Unico Maternità e Paternità (D.Lgs. 151/2001)",
    "tupi": "Testo Unico Pubblico Impiego (D.Lgs. 165/2001)",
    "tus": "Testo Unico Stupefacenti (D.P.R. 309/1990)",
    "tusl": "Testo Unico Sicurezza sul Lavoro (D.Lgs. 81/2008)",
    "wb": "Whistleblowing (D.Lgs. 24/2023)",
    "wbdir": "Direttiva whistleblowing (Dir. UE 2019/1937)",
}
