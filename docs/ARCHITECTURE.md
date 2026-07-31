# Architettura di Caucus

> Questo documento descrive il sistema **come è oggi** (2026-07-31). Le parti
> future sono marcate esplicitamente come roadmap. La storia delle decisioni è
> in `docs/ADR/` e nel git log; il gap analysis che ha guidato questa
> architettura è in `docs/AUDIT_SOTA_2026-07-31.md`.

## 1. Principi

1. **Trust layer prima di tutto** — ogni citazione normativa generata è
   validata post-generazione contro il database (esistenza, fonte, vigenza,
   abrogazione, presenza nel contesto). Il sistema preferisce ammettere un
   gap che inventare una norma.
2. **Il benchmark è l'arbitro** — ogni modifica di qualità si misura su
   Caucus Bench (`benchmark/`), mai su impressioni.
3. **Determinismo dove possibile** — il lookup per numero di articolo batte
   sempre il retrieval probabilistico; i segnali deterministici (riferimenti
   espliciti, abrogazione) correggono i punteggi neurali, non viceversa.
4. **Separation of concerns** — `rag-core` è l'unica libreria che parla con
   LLM/vector store; `ingestion` produce un modello canonico unico
   (`CanonicalAct`) qualunque sia la fonte; l'API li consuma.

## 2. Componenti

```
apps/web        Next.js 15 — chat SSE, pannello fonti, warning citazioni
apps/api        FastAPI — /chat (SSE), /search, /health; auth token; rate limit
services/rag-core     retriever ibrido, rerankers, query expansion,
                      act registry, hit merge (RRF pesato), schemi Pydantic
services/ingestion    parser Normattiva AKN + EUR-Lex HTML + SentenzeWeb,
                      chunker contestuale, loader idempotenti
services/indexer      worker Dramatiq (refresh schedulabile)
benchmark/            Caucus Bench (MIT): gold set + harness
```

Infra locale (docker compose): Postgres 16 + pgvector + FTS `italian_unaccent`
(:55432), Qdrant (:6333), Redis, Langfuse†, MinIO†.
† container presenti ma non ancora integrati nel codice (roadmap: observability
e storage documenti).

## 3. Pipeline di ingestion

Tre fonti, un solo modello canonico (`CanonicalAct` → `Loader`):

| Fonte | Formato | Note |
|---|---|---|
| Normattiva (50 fonti) | Akoma Ntoso XML | due serializzazioni (flat-per-attachment per i codici storici, canonica per i moderni) + caso codici-in-allegato (CPA); rilevamento abrogazioni; data consolidato da FRBRdate/dataVigenza; estrazione `<ref>` per il grafo dei rinvii |
| EUR-Lex (14 atti) | HTML per CELEX | tre generazioni di markup (oj/eli/pre-2010); testo base GU, consolidato in roadmap |
| Cassazione (SentenzeWeb) | JSON (proxy Solr pubblico) | testo integrale anonimizzato; harvest incrementale idempotente per external_id; scarto documenti in oscuramento; 0.5 req/s |

Proprietà dei loader: **delete-and-replace per fonte** (re-run = stesso
corpus, mai duplicati) per le norme; **append-only per external_id** per la
giurisprudenza. Ogni chunk porta un header contestuale
(`[Fonte] Codice Civile — art. 2043 (Rubrica), comma 1`) così il contesto sta
nel testo embeddato, e i campi `effective_from`/`effective_to` per il filtro
di vigenza.

Il grafo dei rinvii (`norm_citation`) è popolato dai `<ref href>` dell'XML,
con target denormalizzato per sopravvivere ai reload e ri-risoluzione
automatica dei link entranti a ogni ingest.

## 4. Pipeline di retrieval (per query)

```
route_query ──► estremi espliciti? ──sì──► lookup diretto (pinnato)
     │                                     [espansione LLM skippata]
     │no
     ▼
query expansion LLM (gpt-4o-mini, ~1s, parallela ai rami DB)
     │  "responsabilità extracontrattuale" → "…art. 2043 codice civile, danno ingiusto…"
     ▼
4 rami → RRF pesato [direct 3.0 | expansion-refs 1.5 | FTS 1.0 | dense 1.0]
     │    • expansion-refs: estremi citati dall'espansione, risolti via act
     │      registry ("D.Lgs. 81/2008"→tusl), MAI pinnati (l'LLM può sbagliare)
     │    • FTS: websearch AND, fallback OR senza boost
     │    • dense: Qdrant, collections codici+cassazione, filtro vigenza
     ▼
cross-encoder bge-reranker-v2-m3 (locale, MPS) sui top-30
     │    riceve la QUERY ESPANSA (misurato: 0.98 vs 0.0002 con la nuda)
     │    correttivi: +1.0 direct, malus abrogato solo sui rami probabilistici
     ▼
dedup per articolo → one-hop expansion sul grafo dei rinvii (max 3)
     ▼
contesto → generazione (gpt-4o) → validazione citazioni → SSE
```

Latenza retrieval misurata: 1.8s (riferimento esplicito) / 2.7s (concettuale).

Vincolo appreso sul campo: le chiamate sulla stessa `AsyncSession` SQLAlchemy
devono restare sequenziali (mai `gather` sui rami DB).

## 5. Trust layer

Post-generazione, su ogni risposta:
1. le citazioni in prosa riconosciute (sigle, forme lunghe, estremi ufficiali)
   vengono promosse a tag `<cite/>` se presenti nel contesto;
2. ogni tag è verificato su DB: fonte indicizzata? articolo esistente?
   vigente alla data? abrogato?
3. le citazioni valide ma assenti dal contesto sono marcate *weak grounding*;
4. l'evento SSE `citation_warnings` porta tutto alla UI; `done` include il
   testo finale con i tag promossi.

La giurisprudenza si cita solo in prosa con gli estremi reali del contesto —
il prompt vieta di inventare estremi e il gold set lo verifica.

## 6. Sicurezza (implementata)

Token auth (fail-closed fuori da `app_env=local`), rate limit per IP, CORS da
env, cap su history (40 turni × 8k char), `tenant_id` mai client-supplied,
errori interni mai esposti, container non-root, sessione DB aperta dentro il
generatore SSE. Dettagli e roadmap (RLS, multi-tenancy, audit log):
`docs/SECURITY.md`.

## 7. Configurazione

Tutto via env (`.env.example` documentato): backend LLM/embedding
(openai/ollama/local/vertex), modelli, device del reranker (cpu/mps/cuda),
candidati rerank, query expansion on/off, auth, rate limit. La factory degli
embedding verifica la coerenza `EMBEDDING_DIM`/backend al boot; il mismatch di
dimensioni della collection Qdrant è un errore esplicito, mai una
cancellazione silenziosa.

## 8. Roadmap architetturale

Multivigenza storica (Normattiva `dataVigenza` per versioni passate);
embedding self-hosted BGE-M3 (dense+sparse, il codice c'è già — richiede
re-ingest); citazioni in structured output; conversazioni server-side + audit
log; observability Langfuse; deploy di riferimento (l'attuale
`infra/terraform` è parziale e non allineato — vedi RELEASE_CHECKLIST).
