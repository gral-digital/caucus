# Architettura

> Questo documento è la **fonte di verità** per le decisioni architetturali. Tutte le scelte qui devono essere discusse prima di essere rimesse in discussione nel codice.

## 1. Principi guida

1. **Sovranità dei dati EU** — tutto il piano dati risiede in regione `europe-west1`. Nessun provider US può processare dati cliente senza DPA conforme GDPR + compatibile con segreto professionale (art. 622 c.p.).
2. **Citation-grounded, non hallucination-prone** — ogni risposta deve contenere riferimenti normativi esatti (`codice:libro:titolo:capo:articolo:comma`) linkabili al testo sorgente. Se il retriever non trova base autoritativa, il sistema dice "non ho trovato" — mai generazione libera su domini giuridici.
3. **Riuso di OSS maturo** — non reimplementare vector DB, parser PDF, orchestratori. Integrare. Contribuire upstream quando serve.
4. **Separation of concerns rigida** — `rag-core` è l'unica libreria che parla con LLM/vector DB. API e workers la consumano. Sostituire un componente (es. Qdrant → Weaviate) deve toccare un solo modulo.
5. **Progressive hardening** — Fase 1 gira con managed services (Vertex AI inference, Cloud SQL). Fase 2+ sposta pezzi su GKE dedicato quando il volume lo giustifica. Stessa codebase.

## 2. Diagramma logico

```
┌────────────────────────────────────────────────────────────────┐
│                         Utente (avvocato)                      │
└──────────────────────────────┬─────────────────────────────────┘
                               │ HTTPS
                  ┌────────────▼─────────────┐
                  │   Next.js 15 (web)       │    Cloud Run (europe-west1)
                  │   App Router, RSC        │    Edge caching via Cloud CDN
                  └────────────┬─────────────┘
                               │ RPC (server actions) / REST
                  ┌────────────▼─────────────┐
                  │   FastAPI (api)          │    Cloud Run
                  │   Auth, routing, SSE     │
                  └─────┬──────────┬─────────┘
         ┌──────────────┤          ├──────────────────┐
         │              │          │                  │
    ┌────▼────┐   ┌─────▼────┐ ┌───▼──────────┐   ┌──▼────────┐
    │ rag-core│   │ Postgres │ │ Qdrant       │   │ Redis     │
    │ library │   │ + pgvec  │ │ (Rust)       │   │ (cache)   │
    │(in-proc)│   │ Cloud SQL│ │ GKE Autopilot│   │ Memorystore│
    └────┬────┘   └──────────┘ └──────────────┘   └───────────┘
         │ LiteLLM
    ┌────▼─────────────────────────────────────┐
    │  Vertex AI Model Garden (europe-west*)   │
    │  - Llama 3.3 70B Instruct (primario)     │
    │  - Gemma 3 (task leggeri)                │
    │  - Claude Sonnet (fallback hard reasoning)│
    │  - text-embedding / bge-m3 via endpoint  │
    └──────────────────────────────────────────┘

    ┌────────────────────────────────────────┐
    │ Workers (Dramatiq su Cloud Run Jobs)   │
    │ - ingestion Normattiva / Cassazione    │
    │ - re-embedding, re-ranking training    │
    │ - document analysis async pipelines    │
    └────────────────────────────────────────┘

    ┌────────────────────────────────────────┐
    │ Observability                          │
    │ - Langfuse (self-hosted) → LLM traces  │
    │ - OpenTelemetry → Cloud Trace/Logging  │
    │ - Sentry → frontend + API errors       │
    └────────────────────────────────────────┘
```

## 3. Stack scelto

| Layer | Tecnologia | Perché |
|-------|------------|--------|
| Frontend | Next.js 15 + React 19 + TypeScript 5 | App Router, RSC streaming, server actions — best DX per chat UI complessa con citazioni |
| UI kit | shadcn/ui + Tailwind CSS v4 | Copy-paste, type-safe, override libero |
| Backend API | Python 3.12 + FastAPI + Pydantic v2 + Uvicorn | Async-first, ecosistema AI nativo, contract-first con OpenAPI |
| Monorepo | pnpm workspaces + Turborepo + uv workspace | Caching build, lock riproducibili |
| Relational DB | Postgres 16 + pgvector + `unaccent` + tsvector italiano | Single-store per metadata + hybrid search rerank |
| Vector DB | Qdrant (v1.12+) | Filtering avanzato (gerarchie normative), sparse+dense nativo, EU-friendly, Rust |
| Queue / cache | Redis 7 (Memorystore) + Dramatiq | Più semplice di Celery, prestazioni solide |
| LLM routing | LiteLLM proxy | Multi-provider, caching, fallback chain, cost tracking |
| LLM inference | Vertex AI Model Garden | Llama/Gemma hosted in EU, pay-per-token, DPA Google |
| Embeddings | BAAI/bge-m3 | Multilingual (ottimo italiano), dense+sparse+ColBERT, 8k context |
| Reranker | BAAI/bge-reranker-v2-m3 (+ fine-tune Italian-LegalBERT in fase 2) | Precisione su cite-exactness |
| PDF parsing | Docling (IBM) | Leader 2025 su layout PDF complessi (atti, sentenze) |
| Chunking | LlamaIndex SemanticSplitter + legal-aware splitter custom | Preserva gerarchia articolo/comma/lettera |
| Agent framework | LangGraph | State machine, durable execution, debuggabile |
| Connectors enterprise | Onyx (da fase 2) | Maturo per Drive/SharePoint/Confluence, evita reinventare |
| Observability LLM | Langfuse (self-hosted) | Tracing prompt, eval, cost attribution, EU-friendly |
| Tracing generale | OpenTelemetry → Google Cloud Trace | Standard aperto |
| Auth | Clerk o Auth.js v5 (fase 1) → SSO SAML/OIDC via WorkOS (fase 2) | Pragmatico ora, enterprise-ready dopo |
| IaC | Terraform | Standard GCP, riproducibile |
| CI/CD | GitHub Actions + Cloud Build | Gratis fino a certe soglie |

## 4. Moduli (da MVP a prodotto completo)

### 4.1 Fase 1 — "Chiedi al Codice"
Input: domanda in linguaggio naturale.
Output: risposta con citazioni precise (articolo, comma) a Codice Civile o Penale.

Pipeline:
```
query → embed (bge-m3) → Qdrant hybrid search (filter: codice)
      → top-50 retrieval → rerank (bge-reranker) → top-8
      → Postgres expand (articoli adiacenti, note, modifiche)
      → LLM (Llama 3.3 70B, prompt con instructions "cita sempre")
      → streaming response SSE con <citation id="art-2043-cc"/>
      → frontend render con link cliccabili
```

Non-goal di fase 1: multi-turn follow-up con memoria lunga, ricerca giurisprudenza, upload documenti.

### 4.2 Fase 2 — Analisi Documenti
Input: upload PDF/DOCX (atto, contratto).
Output: analisi strutturata (parti, oggetto, clausole critiche, red flags, riferimenti normativi).

Pipeline:
```
upload → GCS → Docling parse → chunking → extraction agent (LangGraph)
       → per-section analysis (ragionamento su LLM) → red flags detector
       → output strutturato (JSON schema stabile) + report HTML/PDF
```

Riusa `rag-core` per verificare ogni clausola citata contro Codice e giurisprudenza.

### 4.3 Fase 3 — Drafting assistito
Input: template + fatti + vincoli.
Output: bozza di atto/contratto.

Pipeline LangGraph multi-step con validazione normativa intermedia. Usa `rag-core` per fact-checking ogni riferimento generato.

### 4.4 Fase 4 — Giurisprudenza
Ingestion Cassazione (sezioni civili e penali) da `italgiure.giustizia.it`. Sentence-level chunking con metadata strutturati (sezione, n. sentenza, data, materia, norme citate). Ricerca semantica con filtri e time-decay.

### 4.5 Fase 5 — Enterprise
Onyx connectors per knowledge base studio cliente (Drive, SharePoint, OneDrive), multi-tenancy stretto (RLS Postgres + isolation Qdrant per collection), SSO SAML/OIDC, audit log immutabile (Cloud Storage + WORM).

## 5. Flusso dati e tenancy

- **Dati pubblici** (codici, Gazzetta, Cassazione): indicizzati una volta, shared-read per tutti i tenant.
- **Dati del tenant** (documenti caricati, conversazioni, note): isolati per `tenant_id` a livello:
  - Postgres: row-level security (RLS) su `tenant_id`.
  - Qdrant: collection separata per tenant su dati privati (`tenant_<id>_docs`).
  - GCS: bucket per-tenant oppure prefix + IAM condition.
- **Crypto**: in-transit TLS 1.3 ovunque, at-rest default GCP (AES-256), CMEK opzionale per tenant enterprise.

## 6. Environments

| Env | Dove | Uso |
|-----|------|-----|
| `local` | docker-compose | Dev quotidiano |
| `dev` | GCP project `avvocato-dev` | Integration, staging |
| `prod` | GCP project `avvocato-prod` | Clienti |

Separazione forte dei progetti GCP (zero cross-project IAM).

## 7. Decisioni rifiutate (con motivazione)

| Opzione | Rifiutata perché |
|---------|------------------|
| LangChain core | Astrazione leaky, breaking changes frequenti. Usiamo LangGraph (più stabile) + SDK nativi dove possibile. |
| Pinecone | Vendor US, non necessario vista la qualità di Qdrant EU-self-hostable. |
| MongoDB / Elasticsearch come primario | Postgres + pgvector + Qdrant copre meglio i bisogni con meno moving parts. |
| Ollama in produzione | Ottimo per dev locale, non enterprise-ready per concurrency/SLA. Usiamo Vertex/vLLM. |
| NestJS backend | Ecosistema AI Python è 10× più maturo di Node. TypeScript solo al frontend. |
| Supabase | Buono come prodotto ma non è il fit migliore per un backend Python-heavy con agent orchestration complesso. |

## 8. Open issues

Lista viva — spostare in ADR quando decise.

- [ ] Scelta definitiva auth fase 1: Clerk (rapido, US-hosted con EU residency opz.) vs Auth.js v5 (self-hosted, più lavoro).
- [ ] Qdrant Cloud EU vs self-host su GKE (costo vs operabilità).
- [ ] Training set per fine-tune Italian-LegalBERT come reranker di dominio.
- [ ] Strategia evaluation: dataset gold di domande-risposte verificate da avvocato partner.
- [ ] Ingestione Cassazione: parsing sentenze PDF vs XML DOGI (se disponibile).
