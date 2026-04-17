# ADR 0001 — Stack iniziale

- **Data**: 2026-04-17
- **Stato**: Accettato
- **Decisori**: founder

## Contesto

Partiamo da zero una piattaforma AI legale italiana ("Harvey italiano"). Vincoli:
sovranità dei dati EU, bootstrap solo, costi bassi, volontà di uso di OSS maturo,
roadmap multi-modulo (Q&A, analisi documenti, drafting, giurisprudenza).

## Decisione

- **Hosting**: GCP `europe-west1`. Cloud Run + Cloud SQL + Memorystore.
- **LLM**: Vertex AI Model Garden per Llama 3.3 70B (primario) + Claude Sonnet (fallback).
  Niente self-hosted GPU in fase 1 (antieconomico per solo-dev bootstrap).
- **Backend**: Python 3.12 + FastAPI async.
- **Frontend**: Next.js 15 + React 19 + TypeScript + Tailwind.
- **Monorepo**: pnpm workspaces + Turborepo (Node) + uv workspace (Python).
- **Vector DB**: Qdrant (self-host su GKE in prod, docker-compose in dev).
- **Relational DB**: Postgres 16 con pgvector + FTS italiana (`italian_unaccent`).
- **Embeddings**: bge-m3 (dense + sparse hybrid).
- **Reranker**: bge-reranker-v2-m3 (fase 2: fine-tune su LegalBERT IT).
- **PDF parsing**: Docling (IBM).
- **Agent**: LangGraph (no LangChain core).
- **LLM gateway**: LiteLLM.
- **Connectors enterprise**: Onyx (fase 2+).
- **Observability LLM**: Langfuse self-hosted.
- **Auth fase 1**: Clerk o Auth.js v5 (OPEN — decisione separata).

## Conseguenze

**Positive**
- Tutto EU-sovereign e GDPR/art. 622 c.p. compatibile dal primo giorno.
- Stesso codice dev → prod; scale-to-zero su Cloud Run mantiene idle cost quasi nullo.
- LangGraph + LiteLLM permettono di cambiare modello e orchestrazione senza refactor profondi.

**Negative**
- Dipendenza da Google per Vertex AI: mitigata da LiteLLM che permette switch a vLLM/Fireworks se serve.
- Qdrant in prod richiede GKE operations (mitigato: Qdrant Cloud EU è un'alternativa managed).

## Alternative scartate

Vedi `docs/ARCHITECTURE.md §7` per il dettaglio: LangChain core (instabile), Pinecone (US),
MongoDB/Elastic (non serve), Ollama (non enterprise-ready), NestJS (Python AI ecosystem migliore),
Supabase (fit non ottimale per backend Python-heavy).
