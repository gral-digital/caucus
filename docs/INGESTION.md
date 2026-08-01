# Ingestion

> ⚠️ **STATO (2026-07-31)**: documento parzialmente storico (descrive la
> pipeline della fase CC/CP). La pipeline reale copre oggi 50 fonti
> Normattiva + 14 atti EUR-Lex + Cassazione (SentenzeWeb); vedi
> `docs/ARCHITECTURE.md` §3. Non ancora implementati rispetto a quanto sotto:
> scheduling automatico del refresh, snapshot su GCS, diff-awareness sul
> source_hash. I numeri di coverage citati sotto sono precedenti ai fix del
> parser (2026-07-31) e sono migliorati.

Pipeline di ingestione delle fonti normative italiane. Idempotente, versionata, diff-aware.

## 1. Fonti primarie

| Fonte | Formato | Uso | Status |
|-------|---------|-----|--------|
| **Normattiva** (`normattiva.it`) | **Akoma Ntoso 3.0 XML** | Codici, leggi, d.lgs. | ✅ Implementato |
| Cassazione (italgiure) | HTML + PDF (Docling) | Sentenze, massime | Fase 4 |
| Gazzetta Ufficiale | HTML + RSS | Monitoring modifiche | Fase 4 |
| Documenti del tenant | PDF/DOCX via Docling | Cartelle clienti | Fase 2 |

**Scelta Normattiva AKN**: vedi [ADR-0002](ADR/0002-normattiva-akn.md) per il
rationale. In sintesi: unica fonte autorevole + pubblico dominio + gerarchia
machine-readable (formato OASIS).

## 2. Pipeline generica

```
fetch → cache (GCS/local) → validate (hash, size)
      → parse (→ CanonicalAct)
      → chunk (legal-aware: articolo-full + per-comma + window)
      → embed (bge-m3)
      → upsert Postgres (norm_source, norm_partition, norm_comma, norm_chunk)
      → upsert Qdrant (collection: codici / leggi / cassazione)
      → sanity checks (coverage, count)
```

Ogni stadio scrive snapshot in `data/sources/<source>/<timestamp>/`, così si
può fare rollback e rerun parziali.

## 3. Normattiva: Akoma Ntoso XML

### URN supportati

| Codice | URN | short_id |
|--------|-----|----------|
| Civile | `urn:nir:stato:regio.decreto:1942-03-16;262` | `cc` |
| Penale | `urn:nir:stato:regio.decreto:1930-10-19;1398` | `cp` |
| Procedura Civile | `urn:nir:stato:regio.decreto:1940-10-28;1443` | `cpc` |
| Procedura Penale | `urn:nir:stato:decreto.del.presidente.della.repubblica:1988-09-22;447` | `cpp` |

### Protocollo di download

Normattiva **richiede una sessione cookie**: il link diretto a `caricaAKN`
non funziona senza aver prima visitato il permalink.

1. **Pagina permalink** (necessaria per i cookie di sessione):
   ```
   GET https://www.normattiva.it/uri-res/N2Ls?{urn}
   ```
   Nell'HTML c'è un link `caricaAKN?dataGU=...&codiceRedaz=...&dataVigenza=...`.
   Estraiamo i tre parametri via regex.

2. **Download AKN XML**:
   ```
   GET https://www.normattiva.it/do/atto/caricaAKN?dataGU=X&codiceRedaz=Y&dataVigenza=Z
   ```
   Risposta: `application/xml` Akoma Ntoso 3.0.

Implementazione: [`services/ingestion/src/caucus_ingestion/fetchers/normattiva.py`](../services/ingestion/src/caucus_ingestion/fetchers/normattiva.py).

### Struttura AKN Normattiva

Normattiva serializza l'AKN in un formato "flat":
- `<akomaNtoso>` → `<act>` → `<attachments>` → N `<attachment>` (uno per articolo)
- Ogni `<attachment>` contiene un `<doc name="CODICE CIVILE-art. 2043">` con
  un singolo `<mainBody><paragraph><content><p>` che tiene TUTTO il testo
  dell'articolo (rubrica + commi concatenati con `\n \n`).
- Il testo usa `(( ... ))` per marcare passaggi introdotti da modifiche.
- Dopo il testo vigente, Normattiva accoda note `-----------\nAGGIORNAMENTO (N)`
  con descrizione delle modifiche storiche; il parser le separa in metadata.

La gerarchia Libro/Titolo/Capo/Sezione **non** è codificata a livello di
articolo nell'XML servito da Normattiva. Il parser iniziale flattisce tutti
gli articoli sotto un'unica root. Arricchimento gerarchico previsto in fase 2.

### Coverage attuale (fixture 2026-04-17)

| Codice | Articoli totali | Articoli attivi | Rubriche riconosciute |
|--------|----------------:|----------------:|----------------------:|
| CC | 3261 | 2946 | 2728 / 2946 = **92.6%** |
| CP | 987  | 768  | 699 / 768 = **91.0%** |

Le rubriche non riconosciute cadono quasi tutte su articoli abrogati/soppressi
(che non hanno più rubrica per definizione).

## 4. Comandi

### Scaricare fixture (con connessione)

```bash
# Scarica e salva XML AKN sotto data/fixtures/normattiva/
make fetch-codici
# oppure singolo:
uv run caucus-ingest fetch --codice cc
```

### Parse-only (sanity check)

```bash
make parse-codici
# Output:
# ✓ cc parsato: 3261 articoli, 2838 con rubrica (87.0%)
# ✓ cp parsato: 987 articoli, 827 con rubrica (83.8%)
```

### Ingestion completa (Postgres + Qdrant)

```bash
# Richiede `make up` già attivo (Postgres, Qdrant) e `make migrate` già eseguito.
make seed-codice-civile   # CC
make seed-codice-penale   # CP
```

### Ingestion veloce senza embedding (iterazione dev)

```bash
make seed-codici-fast
# Popola norm_source/partition/comma/chunk in Postgres
# ma non calcola embedding né fa upsert su Qdrant.
# Usare dopo: reindex con worker dedicato.
```

## 5. Chunking legal-aware

Tre livelli di chunk per ogni articolo, tutti indicizzati:

1. **Articolo completo** (`articolo-full`): rubrica + tutti i commi. Buono per
   query del tipo "cos'è l'art. 2043".
2. **Comma singolo** (`comma`): un chunk per comma. Fine-grained.
3. **Window scorrevole** (`window`): finestra 2048 char / overlap 256, solo
   per articoli molto lunghi (>2k token). Coprire ricerche in linguaggio
   naturale che non mappano a una struttura precisa.

Il retriever fa hybrid search su tutti; il reranker sceglie; l'expander
Postgres recupera il contesto gerarchico (articoli adiacenti, rubrica).

Dettaglio: `services/ingestion/src/caucus_ingestion/chunker.py`.

## 6. Versioning

Ogni `norm_partition` e `norm_comma` ha `effective_from` / `effective_to`.
Quando Normattiva serve una versione con testo cambiato:
- Il vecchio record resta, con `effective_to = data modifica`.
- Ne viene creato uno nuovo con `effective_from = data modifica`, `effective_to = NULL`.

Query a data X:
```sql
WHERE effective_from <= X
  AND (effective_to IS NULL OR effective_to > X)
```

## 7. Schedule (prod)

| Fonte | Schedule | Tool |
|-------|----------|------|
| Codici (CC, CP, CPC, CPP) | Weekly (lun 03:00 CET) | Cloud Scheduler → Cloud Run Job |
| Cassazione massime | Daily (04:00 CET) | idem (fase 4) |
| Cassazione sentenze | On-demand | Cloud Tasks (fase 4) |
| Documenti tenant | Event-driven (upload) | Pub/Sub → Cloud Run (fase 2) |

## 8. Quality checks

Dopo ogni run di ingestion:
- Conteggio articoli per codice vs reference range (CC 3100-3400, CP 900-1100).
- Coverage rubriche su articoli attivi ≥ 85%.
- Articoli famosi sentinel: CC 2043, 1418, 414 / CP 575, 416-bis, 612-bis hanno
  rubrica corretta (test parametrizzati).
- Test completi in `services/ingestion/tests/test_normattiva_akn_parser.py`.

## 9. Fonti rifiutate

Vedi ADR-0002 per il dettaglio.

- **Wikisource**: ferma al 2022, non aggiornata con riforma Cartabia 2022 e modifiche 2023-2025.
- **HuggingFace datasets** (`mii-llm/gazzetta-ufficiale`, `joelniklaus/Multi_Legal_Pile`): non contengono i Codici vigenti consolidati.
- **Brocardi.it, Altalex**: ToU ostili a scraping; annotazioni coperte da copyright.
- **Normattiva export form** (`/esporta/attoCompleto`): richiede autenticazione, non usabile programmaticamente.
