# Avvocato

Piattaforma AI enterprise per il settore legale italiano — RAG su Codice Civile, Codice Penale e giurisprudenza, drafting e analisi documenti.

## Stato

Fase 0 — scaffolding architettura. Il primo modulo in consegna è **"Chiedi al Codice"** (Q&A su Codice Civile e Penale con citazioni precise articolo:comma).

## Architettura (riassunto)

- **Backend**: Python 3.12, FastAPI async
- **Frontend**: Next.js 15, React 19, TypeScript, shadcn/ui
- **Monorepo**: pnpm workspaces + Turborepo per Node, uv workspace per Python
- **Vector DB**: Qdrant (EU-self-hosted)
- **Relational DB**: Postgres 16 + pgvector + FTS italiano (Cloud SQL)
- **Cache / queues**: Redis (Memorystore)
- **LLM routing**: LiteLLM con Llama 3.3 70B (Vertex AI) primario + Claude Sonnet fallback
- **Embeddings**: BAAI/bge-m3 (multilingual, dense+sparse)
- **Reranker**: bge-reranker-v2-m3 + Italian-LegalBERT fine-tune (fase 2)
- **Parsing giuridico**: Docling (IBM)
- **Agent orchestration**: LangGraph
- **Observability**: Langfuse self-hosted + OpenTelemetry
- **Hosting**: GCP `europe-west1` (sovranità dati EU + GDPR + segreto professionale art. 622 c.p.)

Vedi [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) per i dettagli.

## Quick start (dev locale)

Prerequisiti: Docker, `uv`, `pnpm`, `node >= 20`.

```bash
# 1. Dipendenze
make install

# 2. Infra locale (Postgres, Qdrant, Redis, Langfuse)
make up

# 3. Migration + seed iniziale
make migrate
make seed-codice-civile   # scarica da Normattiva, parse, indicizza

# 4. Avvia API + web in dev
make dev
```

API su http://localhost:8000/docs · Web su http://localhost:3000 · Langfuse su http://localhost:3001.

## Layout repository

```
apps/
  web/              Next.js 15 frontend (App Router)
  api/              FastAPI backend (chat, search, auth)
services/
  ingestion/        Pipeline Normattiva → Qdrant+Postgres
  indexer/          Re-indexing, embedding workers
  rag-core/         Libreria Python: retriever, reranker, LLM router
packages/
  shared-types/     Tipi TS generati da Pydantic schemas
  ui/               Design system (shadcn/ui components)
infra/
  terraform/        GCP IaC (Cloud Run, SQL, Memorystore, GKE, GCS)
  k8s/              Qdrant StatefulSet, vLLM deployment (fase 2)
data/
  sources/          Snapshot testi normativi (GCS-backed, gitignored)
  schemas/          JSON Schema per articoli, commi, sentenze
docs/               Architettura, data model, sicurezza, runbook
```

## Moduli (roadmap)

| Fase | Modulo | Stato |
|------|--------|-------|
| 1 | Chiedi al Codice (Civile + Penale) | In corso |
| 2 | Analisi Documenti (atti, contratti, red flags) | Progettato |
| 3 | Drafting assistito (atti, contratti) | Progettato |
| 4 | Giurisprudenza (Cassazione) | Progettato |
| 5 | Onyx connectors + multi-tenancy + SSO | Progettato |

Dettagli in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Sicurezza

Dati legali italiani = segreto professionale (art. 622 c.p.) + GDPR. Vedi [docs/SECURITY.md](docs/SECURITY.md).

## Licenza

Proprietaria, salvo diverso avviso sui singoli sotto-package.
