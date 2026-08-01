# Handoff: Caucus

> Passaggio di consegne (2026-07-31). Questo documento porta un nuovo agente/
> sviluppatore da zero contesto a operativo. Leggilo tutto prima di toccare
> il codice. (Il progetto si chiama **Caucus**; la directory di lavoro locale
> può avere ancora il vecchio nome `avvocato`.)

## 1. Cos'è

Assistente legale RAG open source sul diritto italiano, con trust layer che
valida ogni citazione, e **Caucus Bench**: il primo benchmark legale italiano
aperto. Obiettivo dichiarato dall'owner: "agente open source SOTA per legal e
compliance in Italia, deve essere perfetto/impeccabile". **Non ancora
pubblicato**: nessun remote git configurato (`git remote -v` è vuoto).

Il posizionamento è "numeri onesti": codice AGPL-3.0, benchmark MIT, metriche
riproducibili contro claim di marketing dei competitor (Lexroom dichiara "97%"
non verificabile). Questo vincola lo stile: **mai gonfiare i numeri, mai
documentare aspirazioni come feature, sempre misurare sul benchmark.**

## 2. Stato in una riga

Funzionante e verificato. Ultimo eval 171 casi (gold v2.3, stack idle):
**pass 97.7%, pass(hard) 100%, recall@8 99.4%, MRR 0.86, citation recall
98.5%, hallucination 0%, over-refusal 0%, refusal adversarial 100%, gap
admission 100%, TTFT p50 4.7s**. Varianza tra run della stessa config: pass
95.3–97.7%, recall 96.2–99.4: il numero onesto è l'intervallo, non il
picco. 106 test Python + 9 TS verdi, build di produzione Next ok, ruff+mypy
strict+tsc+eslint puliti, CI bloccante. Test E2E completo dei flussi
prodotto eseguito il 2026-07-31 sera (ricerca+link /norma, export, upload+
analisi, redazione, giurisprudenza, validate, taskpane): tutto verde;
UNICA cosa non collaudata: l'add-in dentro Word reale (serve sideload
dell'owner). NB: non lanciare `next build` mentre `next dev` gira (corrompe
la cache .next del dev server; successo e risolto).

## 3. Architettura (dove sta cosa)

Leggi `docs/ARCHITECTURE.md` (aggiornato al reale). In breve:

```
apps/web            Next.js 15: chat SSE, pannello fonti, pagina /norma
apps/api            FastAPI: /chat (SSE), /search, /norma, /health
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
`LLM_PRIMARY_MODEL=openai/gpt-4o`, `QUERY_EXPANSION_MODEL=openai/gpt-4o`
(aggiunto: il default in config resta gpt-4o-mini, ma la config di riferimento
usa 4o, misurato molto più preciso sugli articoli), `RERANKER_BACKEND=local`,
`RERANKER_DEVICE=mps`. Un eval completo (171 casi) costa nell'ordine di 1-2€
di API OpenAI: misurare con criterio, non a raffica.

## 5. Regole di lavoro apprese (non ripetere gli errori)

- **Il benchmark è l'arbitro.** Ogni cambiamento di qualità → `make eval`
  prima/dopo, confronto con `--baseline`. Il gold set NON si adatta mai
  all'output del sistema (è come la v1 barava).
- **Mai `gather` su più chiamate della stessa `AsyncSession` SQLAlchemy**:
  crash "session is provisioning a new connection". I rami DB in
  `search_service.py` restano sequenziali; solo espansione LLM (HTTP) e ramo
  vettoriale (Qdrant) sono paralleli.
- **macOS non ha `setsid`.** Per processi persistenti: `nohup … & disown`,
  poi verifica con `pgrep`. L'harvest è morto due volte per questo.
- **Il reranker va alimentato con la query ESPANSA**, non l'originale
  (misurato: 0.98 vs 0.0002 sull'articolo giusto).
- **FlagEmbedding è rotto** con transformers recenti → si usa
  `sentence_transformers.CrossEncoder`.
- **Verifica nei log QUALE reranker è attivo prima di ogni eval**
  (`cross_encoder_rerank.done` vs `keyword_rerank.done`): un venv senza
  `sentence-transformers` degradava in silenzio al keyword reranker e ha
  falsato una sessione di misure. Ora l'extra è di default e il fallback
  logga `reranker_local_deps_missing_fallback_keyword`.
- **Niente ramo FTS globale sul testo espanso**: misurato dannoso (chunk
  contati due volte diluiscono il merge RRF: recall 96→92, MRR 0.89→0.77).
  Il ramo FTS *ristretto alle fonti dei candidati d'espansione* (max 8 hit,
  max 3 fonti) invece aiuta ed è in produzione.
- **L'espansione è sul percorso critico del TTFT**: output oltre ~150 token
  con gpt-4o causava timeout (6s) intermittenti → retrieval senza espansione
  → recall 0 su casi random. Budget attuale: 150 token, due righe.
- **Fusione inter-collection**: score RRF di collection diverse NON sono
  comparabili → si fonde per rank con quota per corpus, mai per score.

## 6. Lavori aperti, in ordine di priorità

1. ~~Recall 85%~~ **RISOLTO** (sessione 2026-07-31 sera): espansione
   strutturata multi-candidato (query_expander.py, riga RIF `sigla numero`
   validata su SOURCE_CATALOG) + cross-encoder ripristinato + riparazione
   citazioni. Recall@8 97%, pass 96%. Tail residuo (~5-7 casi, in parte
   flaky per nondeterminismo OpenAI): wb-12 (il modello non conosce i numeri
   interni del d.lgs. 24/2023: servono wb 4+12+17 TUTTI in top-8),
   cds-multi-2054, cpp-335, cpp-438/cost-* ("risposta senza citazioni",
   generazione). NON tentare di nuovo il ramo FTS globale sul testo espanso
   (vedi §5).
2. **Latenza (pass fatto il 2026-07-31 sera)**: TTFT p50 8.7s→4.6s, p95
   23s→10.1s a pari pass/recall (costo: MRR 0.89→0.85, cite recall ~94%).
   Come: espansione → gpt-4.1-mini (A/B sul prompt finale: 9/14 vs 7/14 di
   4o-mini e 6/14 di 4o: il prompt conta più del modello; nano 2/14,
   inutilizzabile), reranker max_length 512→384 (~3s→0.8s), ramo vettoriale
   in parallelo all'espansione (sulla query pre-espansione). Residuo ~4s
   idle = espansione 1.7s + rerank 1s + primo token gpt-4o ~1.5s: per
   scendere ancora servono scelte di prodotto (modello di generazione più
   reattivo, o espansione adattiva), da misurare.
3. **Harvest Cassazione** verso 200k: gira in background
   (`scripts/harvest_cassazione_full.sh`, log `/tmp/harvest_cassazione.log`,
   ~50k fatte). Resumabile e idempotente. Il completo (~430k) costa ~12€ di
   embedding in più → decisione dell'owner. **Attenzione**: più cresce, più può
   ri-abbassare il recall normativo → ri-valutare la `case_law_candidate_ratio`.
4. **Prodotto (fase avviata 2026-07-31, decisione owner: prodotto prima
   delle metriche; si pubblica tutto insieme)**. Fatto: (a) export .docx del
   parere con citazioni ri-verificate server-side (`routes/export.py` +
   `services/docx_export.py` + bottone in ChatView; python-docx); (b) analisi
   documentale v1 (`routes/documents.py` + `services/document_extract.py` +
   tabella `user_document` migrazione 0004 + `ChatRequest.document_ids` +
   graffetta/chip in UI); (c) workspace a tre moduli con
   `ChatRequest.mode` e prompt dedicati per analisi/redazione
   (`Workspace.tsx`, Sidebar navigabile, conversazioni per modulo).
   Scoperto durante i test: manca la L. 431/1998 (locazioni abitative) dal
   corpus: task separato avviato dall'owner. Fatto anche: (d) sidebar
   minimale (catalogo fonti in pannello modale); (e) modulo Giurisprudenza
   (mode dedicato, Cassazione primaria nel retrieval; NB: l'ordine di
   `query.corpora` è ora semantico, il primo è il corpus primario).
   Fatto anche: (f) estratti pertinenti per documenti lunghi
   (document_excerpts.py, testa + finestre rilevanti con omissis marcati);
   (g) Word add-in v0 (apps/word-addin/ + statici in
   apps/web/public/word-addin/, endpoint POST /citations/validate),
   **NON ancora collaudato dentro Word reale**: manifest validato e pagina
   verificata nel browser (SSE ok, endpoint ok); il primo sideload in Word
   (richiede HTTPS: `pnpm dev --experimental-https`) è in checklist
   pre-release insieme alle icone definitive. La fase prodotto
   pre-pubblicazione è COMPLETA: prossimo passo test completo (eval +
   E2E) e poi pubblicazione.
5. **Giurisprudenza di merito: fetcher Giustizia Amministrativa PRONTO**
   (`services/ingestion/.../fetchers/giustizia_amministrativa.py`, 4 test):
   ricerca portlet Liferay (instance id + p_auth estratti a runtime, MAI
   hardcodati), paginazione verificata live (CdS e TAR Milano), testo
   integrale da mdp.* con trim dei metadati interni del gestionale (path di
   rete, operatori: NON devono finire nel corpus). ToS verificati
   2026-07-31: no robots.txt, no clausole anti-riuso, pubblicità legale;
   postura SentenzeWeb (0.5 req/s, UA identificato). PDF storici scartati
   in v1. **Manca il loader**: riusare il pattern cassazione_loader
   (case_law con kind ga_cds/ga_tar_*, display «Cons. St., Sez. IV, n.
   6189/2026» da aggiungere a CaseLawCitation, quota corpus). Costo
   embedding ~7€/100k provvedimenti: partire con CdS ultimi 3 anni + TAR
   Roma/Milano/Napoli. Per il merito CIVILE: la Banca Dati pubblica del
   Ministero (3,5M sentenze) richiede SPID e non consente harvest. Dopo
   la pubblicazione: richiesta formale di accesso programmatico come
   progetto open di interesse pubblico.
6. **Rilascio free (2026-07-31 notte)**: landing a `/` (numeri onesti,
   quattro moduli, trust layer; l'app è su `/app`), thinking onesto in chat
   (eventi SSE `status` con le fasi reali della pipeline, collassati a fine
   risposta), fix UX (input allineato, focus, nuova conversazione senza
   reload). Wordmark tipografico «caucus.» ovunque (niente icona). Gli URL
   GitHub in landing e docs puntano a github.com/gral-digital/caucus (l'org
   caucus-legal non esiste; un eventuale transfer futuro mantiene i redirect). **Streaming**: la compressione del proxy Next bufferizzava
   l'SSE (risposta consegnata in blocco); risolto con compress:false +
   Cache-Control no-transform; se cambi reverse proxy in prod, NON
   comprimere /api/v1/chat (X-Accel-Buffering: no già impostato). **Account
   free tier**: fondamenta pronte dietro `ACCOUNTS_ENABLED` (default off):
   user_account Argon2id + auth_session (solo SHA-256 del token),
   /auth/register|login|logout|me testati E2E, documenti legati all'utente.
   **COMPLETATO il free tier** (stessa notte): enforcement su tutti gli
   endpoint applicativi (401 senza sessione; API_AUTH_TOKEN resta per
   ops/benchmark), quota giornaliera per utente (FREE_DAILY_CHAT_LIMIT,
   upsert atomico su usage_daily, 429 con invito al self-hosting),
   /auth/config pubblico, UI: AuthGate con login/registrazione, badge
   utente + logout in sidebar, Authorization su tutte le chiamate. E2E
   verificato: gate nel browser, registrazione→app, quota 2/2 poi 429,
   default off invariato. Resta SOLO la verifica email (serve un provider
   SMTP: decisione di deployment, non di codice).
7. **Pubblicazione**: tutto pronto, checklist in `docs/RELEASE_CHECKLIST.md`.
   Restano solo azioni che richiedono il repo remoto (creare org GitHub,
   push, private vulnerability reporting, tag v0.1.0). Nome verificato libero.
   **Corpus scaricabile (2026-08-01)**: `make corpus-export` produce il
   pacchetto ridistribuibile (pg dump data-only con snapshot MVCC coerente +
   snapshot Qdrant + manifest con checksum; ~3.9 GB) e `make corpus-import
   SRC=<dir|url>` lo ripristina con verifica integrale; testato end-to-end
   in locale (DB temporaneo + collection di test). Azione owner al publish:
   scegliere l'hosting (i singoli file superano il limite 2 GB dei release
   asset GitHub per la collection cassazione → serve hosting statico tipo
   HuggingFace/R2, o split) e sostituire `SRC=<url>` nei README con l'URL
   reale. **Docs in-app (2026-08-01)**: sezione `/docs` completa nel frontend
   (8 pagine: panoramica, self-hosting, corpus, trust layer, moduli, API,
   benchmark, FAQ), linkata da landing e sidebar.
8. Roadmap qualità: multivigenza storica (Normattiva `dataVigenza`), embedding
   self-hosted BGE-M3 (azzera costi/dipendenza US, il codice c'è già),
   structured output per le citazioni, conversazioni server-side + audit log.

## 7. File da leggere per primi

- `docs/AUDIT_SOTA_2026-07-31.md`: il gap analysis iniziale (competitor,
  SOTA, tecniche). Storico ma utile per il perché delle scelte.
- `benchmark/README.md` + `benchmark/RESULTS.md`: cosa si misura e come.
- `docs/ARCHITECTURE.md`: il sistema com'è.
- `git log --oneline`: la storia ha i numeri prima/dopo in ogni commit.
