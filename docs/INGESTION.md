# Ingestion

Pipeline di ingestione delle fonti normative e giurisprudenziali. Il design è **idempotente**, **versionato** e **diff-aware**: ri-eseguire l'ingestione aggiorna solo ciò che è cambiato.

## 1. Pipeline generica

```
source fetcher → validator (hash) → parser (→ canonical AST)
               → chunker (legal-aware) → embedder (bge-m3)
               → postgres upsert (norm_*)  + qdrant upsert
               → reindex FTS                + citation resolver
               → sanity checks (count, coverage)
```

Ogni stadio scrive snapshot in `data/sources/<source>/<timestamp>/`, così possiamo rollback e rerun parziali.

## 2. Normattiva (Codici, Leggi)

**URL pattern**: `https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:codice.civile`

**Formato preferito**: AkomaNtoso XML quando esposto (rotta `/eli/…`). Fallback HTML parsing con BeautifulSoup.

**Rispetto robots.txt + rate limiting**: max 1 req/s, User-Agent identificabile, retry con backoff esponenziale.

**Parser**: produce `CanonicalAct` (Pydantic model in `services/ingestion/avvocato_ingestion/parsers/canonical.py`) che normalizza libro/titolo/capo/sezione/articolo/comma indipendentemente dal formato sorgente.

**Versioning**: se il testo di un articolo cambia rispetto all'ultima ingestione, si crea un nuovo record con `effective_from = <data modifica>` e si chiude quello vecchio con `effective_to`.

### Comando
```bash
make seed-codice-civile
make seed-codice-penale
# oppure arbitrario:
uv run -m avvocato_ingestion.sources.normattiva --urn urn:nir:stato:codice.civile
```

## 3. Cassazione (italgiure)

**Fonte**: `https://www.italgiure.giustizia.it/sncass/` (Cassazione SN — sentenze e massime).

**Accesso**: richiede user-agent pulito; non è permesso lo scraping massivo aggressivo. Strategia:
- **Massime** (CED): se disponibile export XML/JSON (esistono API CED per istituzioni; da richiedere), preferirlo a scraping.
- **Sentenze integrali**: fetch incrementale (ultime N giorni) + ingestione on-demand.

**Parsing sentenze PDF**: Docling → struttura (intestazione, motivi in fatto, motivi in diritto, PQM).

**Privacy**: rimozione di nomi parti *non* necessaria sui dati Cassazione pubblicati (sono già anonimizzati dalla Corte), ma hashing comunque dei nomi rimanenti per dedup.

## 4. Gazzetta Ufficiale (opzionale fase 4+)

Feed RSS quotidiano + download PDF. Solo atti di pubblicazione normativa rilevanti (codici, leggi, d.lgs., d.l.). Serve principalmente come **trigger di update** su norme esistenti.

## 5. Documenti del tenant (fase 2+)

Upload PDF/DOCX/EML via UI → GCS bucket per-tenant → Cloud Tasks enqueues ingestion job → Docling parse → chunking + embedding → Qdrant collection tenant.

**Quarantine**: antivirus scan (ClamAV o Google Chronicle) prima di aprire il file. Rifiuto se >100MB senza piano enterprise.

## 6. Connectors enterprise (fase 5+)

Integrazione **Onyx** come gateway connettori (Drive, SharePoint, OneDrive, Confluence, Notion, Email). Onyx gestisce OAuth, incremental sync, change detection. Noi consumiamo il suo output normalizzato e lo passiamo al nostro chunker legal-aware.

Perché Onyx e non reimplementare: 40+ connettori già testati in produzione, auth flows consolidati, delta sync robusto.

## 7. Schema di chunking legal-aware

Tre livelli di chunk per ogni articolo, tutti indicizzati:

1. **Articolo completo** (`articolo-full`): un chunk = testo dell'intero articolo + rubrica. Buono per query "cos'è l'art. 2043".
2. **Comma singolo** (`comma`): un chunk per comma. Buono per query fine-grained.
3. **Window scorrevole** (`window`): finestra 512 token con overlap 64, solo per articoli molto lunghi (>2k token). Buono per ricerche in linguaggio naturale che non mappano a struttura.

Il retriever fa hybrid search su tutti, reranker sceglie i migliori, l'expander Postgres recupera il contesto gerarchico (articoli adiacenti, rubrica, commi fratelli).

## 8. Quality checks post-ingestion

Dopo ogni run:
- Conteggio articoli per codice vs reference golden (es. Codice Civile ≈ 2969 articoli).
- Coverage citation resolver: % di citazioni interne risolte.
- Sample 10 articoli casuali → render markdown → ispezione manuale periodica.
- Embedding drift: distanza media tra embedding nuovi e vecchi sugli stessi articoli non modificati (deve essere ≈ 0).

## 9. Schedule

| Fonte | Schedule | Tool |
|-------|----------|------|
| Codici | Weekly (lun 03:00 CET) | Cloud Scheduler → Cloud Run Job |
| Leggi speciali tracked | Weekly | idem |
| Cassazione massime | Daily (04:00 CET) | idem |
| Cassazione sentenze | On-demand | Cloud Tasks |
| Documenti tenant | Event-driven (upload) | Pub/Sub → Cloud Run |
