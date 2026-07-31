# Handoff — Caucus

> Passaggio di consegne (2026-07-31). Questo documento porta un nuovo agente/
> sviluppatore da zero contesto a operativo. Leggilo tutto prima di toccare
> il codice. La directory di lavoro è `/Users/albertomincato/avvocato`
> (il progetto si chiama **Caucus**; la cartella ha ancora il vecchio nome).

## 1. Cos'è

Assistente legale RAG open source sul diritto italiano, con trust layer che
valida ogni citazione, e **Caucus Bench**: il primo benchmark legale italiano
aperto. Obiettivo dichiarato dall'owner: "agente open source SOTA per legal e
compliance in Italia, deve essere perfetto/impeccabile". **Non ancora
pubblicato** — nessun remote git configurato (`git remote -v` è vuoto).

Il posizionamento è "numeri onesti": codice AGPL-3.0, benchmark MIT, metriche
riproducibili contro claim di marketing dei competitor (Lexroom dichiara "97%"
non verificabile). Questo vincola lo stile: **mai gonfiare i numeri, mai
documentare aspirazioni come feature, sempre misurare sul benchmark.**

## 2. Stato in una riga

Funzionante e verificato. Eval 171 casi (gold v2.3): **pass 85%, recall@8 85%,
MRR 0.74, citation recall 90%, hallucination 0%, over-refusal 0%, refusal
adversarial 100%, gap admission 100%, TTFT p50 2.2s**. 78 test Python + 9 TS
verdi, ruff+mypy strict+tsc+eslint puliti, CI bloccante.

## 3. Architettura (dove sta cosa)

Leggi `docs/ARCHITECTURE.md` (aggiornato al reale). In breve:

```
apps/web            Next.js 15 — chat SSE, pannello fonti, pagina /norma
apps/api            FastAPI — /chat (SSE), /search, /norma, /health
services/rag-core   retriever, rerankers, query expansion, act_registry,
                    hit_merge (RRF pesato), query_router, schemi
services/ingestion  parser Normattiva AKN + EUR-Lex + SentenzeWeb,
                    chunker contestuale, loader, CLI `caucus-ingest`
benchmark/          Caucus Bench: gold_cases.json + run_benchmark.py (MIT)
```

**Nota nomi**: i package Python sono `caucus_*` (rinominati). MA container
docker e db/utente Postgres sono ancora `avvocato-*`/`avvocato` di proposito
(rinominarli distrugge i volumi locali col corpus). Non toccarli.

## 4. Come far girare tutto (verificato)

```bash
make up                 # Postgres :55432, Qdrant :6333, Redis, Langfuse, MinIO
make migrate            # alembic → head (20260731_0003)
# corpus GIÀ indicizzato in locale: 50 fonti norme + 14 UE + ~50k sentenze.
# Per rifarlo da zero: make seed-all (norme) + make harvest-cassazione.

# API (nota: il reranker locale si scalda al boot, ~5s):
cd apps/api && RATE_LIMIT_PER_MINUTE=0 uv run uvicorn caucus_api.main:app --port 8000
# poi: make eval  (o: uv run python benchmark/run_benchmark.py --json-out reports/x.json)
```

Env chiave in `.env` (gitignorato, NON committato): `OPENAI_API_KEY` presente,
`LLM_PRIMARY_MODEL=openai/gpt-4o`, `RERANKER_BACKEND=local`,
`RERANKER_DEVICE=mps`. Budget OpenAI usato nella sessione ~15€, autorizzato 30€.

## 5. Regole di lavoro apprese (non ripetere gli errori)

- **Il benchmark è l'arbitro.** Ogni cambiamento di qualità → `make eval`
  prima/dopo, confronto con `--baseline`. Il gold set NON si adatta mai
  all'output del sistema (è come la v1 barava).
- **Mai `gather` su più chiamate della stessa `AsyncSession` SQLAlchemy** —
  crash "session is provisioning a new connection". I rami DB in
  `search_service.py` restano sequenziali; solo espansione LLM (HTTP) e ramo
  vettoriale (Qdrant) sono paralleli.
- **macOS non ha `setsid`.** Per processi persistenti: `nohup … & disown`,
  poi verifica con `pgrep`. L'harvest è morto due volte per questo.
- **Il reranker va alimentato con la query ESPANSA**, non l'originale
  (misurato: 0.98 vs 0.0002 sull'articolo giusto).
- **FlagEmbedding è rotto** con transformers recenti → si usa
  `sentence_transformers.CrossEncoder`.
- **Fusione inter-collection**: score RRF di collection diverse NON sono
  comparabili → si fonde per rank con quota per corpus, mai per score.

## 6. Lavori aperti, in ordine di priorità

1. **Recall 85% non è tornato ai 92%** pre-crescita Cassazione. È il difetto
   n.1 aperto, documentato onestamente in `benchmark/RESULTS.md`. I casi
   residui (vedi `reports/eval_CURRENT_*.json`, campo `failures`) sono query
   concettuali la cui espansione non fa emergere il numero d'articolo giusto
   (es. cc-2946 prescrizione, cc-316, ccii-2, ccp-2/17, cad-20, cts-4). Piste:
   migliorare il prompt d'espansione, o un secondo giro di retrieval sui hit
   deboli, o multi-query.
2. **Harvest Cassazione** verso 200k: gira in background
   (`scripts/harvest_cassazione_full.sh`, log `/tmp/harvest_cassazione.log`,
   ~50k fatte). Resumabile e idempotente. Il completo (~430k) sfora il budget
   (~12€ oltre) → decisione dell'owner. **Attenzione**: più cresce, più può
   ri-abbassare il recall normativo → ri-valutare la `case_law_candidate_ratio`.
3. **Pubblicazione**: tutto pronto, checklist in `docs/RELEASE_CHECKLIST.md`.
   Restano solo azioni che richiedono il repo remoto (creare org GitHub,
   push, private vulnerability reporting, tag v0.1.0). Nome verificato libero.
4. Roadmap qualità: multivigenza storica (Normattiva `dataVigenza`), embedding
   self-hosted BGE-M3 (azzera costi/dipendenza US, il codice c'è già),
   structured output per le citazioni, conversazioni server-side + audit log.

## 7. File da leggere per primi

- `docs/AUDIT_SOTA_2026-07-31.md` — il gap analysis iniziale (competitor,
  SOTA, tecniche). Storico ma utile per il perché delle scelte.
- `benchmark/README.md` + `benchmark/RESULTS.md` — cosa si misura e come.
- `docs/ARCHITECTURE.md` — il sistema com'è.
- `git log --oneline` — la storia ha i numeri prima/dopo in ogni commit.

## 8. Memoria persistente dell'assistente

C'è una memoria di progetto in
`~/.claude/projects/-Users-albertomincato-avvocato/memory/` (caricata a ogni
sessione). Contiene: profilo owner, feedback ricorrenti (assistente orientato
alla difesa; non scaricare modelli >1GB senza conferma; controllo
allucinazioni), e lo stato del progetto. Aggiornala quando cambia qualcosa di
non derivabile dal codice.
