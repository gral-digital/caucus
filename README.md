# Caucus

**Open-source legal & compliance AI for Italian law — with a verifiable trust
layer and the first open Italian legal benchmark.**

*[Versione italiana → README.it.md](README.it.md)*

Caucus is a retrieval-augmented legal assistant over the Italian legal system:
50 consolidated statutes from Normattiva (civil, criminal and procedure codes,
consolidated acts, compliance legislation), 14 EU acts in Italian (GDPR,
AI Act, NIS2, DORA, MiCA…), and the full-text, anonymized decisions of the
Corte di Cassazione. Every normative citation in every answer is validated
post-generation against the corpus — existence, source and temporal validity —
and flagged to the user when it isn't verifiable.

> ⚠️ **Caucus is not a lawyer and its output is not legal advice.** It is a
> research and drafting aid. No professional relationship is created by using
> it. For decisions with legal consequences, consult a licensed professional.

## Why it exists

Legal AI vendors claim accuracy figures that cannot be reproduced. Caucus takes
the opposite bet: **open code (AGPL-3.0), open benchmark (MIT), honest
numbers**. On [Caucus Bench](benchmark/README.md) — 162 cases across all major
areas of Italian law, including repealed articles, adversarial requests and
out-of-corpus questions — the reference stack currently measures:

| | |
|---|---|
| Pass rate | **85%** (78% on hard cases) |
| Source-aware recall@8 / MRR | **85% / 0.74** |
| Citation recall | **90%** |
| **Hallucinated citations** (over citing answers) | **0.0%** |
| Refusal on adversarial requests | **100%** |
| **Over-refusal on legitimate professional questions** | **0%** |

Numbers, methodology and anti-gaming rules: [benchmark/](benchmark/README.md).

## What's inside

- **Corpus** — 50 Normattiva sources parsed from official Akoma Ntoso XML
  (with repeal detection and consolidation dating), 14 EUR-Lex acts in
  Italian, incremental idempotent harvest of Cassazione decisions
  (~430k available, resumable).
- **Retrieval** — four fused branches (weighted RRF): deterministic
  article lookup, LLM query expansion with official-reference resolution
  ("art. 17 D.Lgs. 81/2008" → TU Sicurezza), Postgres FTS (Italian config),
  dense vectors (Qdrant). Cross-encoder reranking (bge-reranker-v2-m3,
  local, MPS/CUDA/CPU). One-hop expansion over the **norm citation graph**
  extracted from the XML cross-references.
- **Trust layer** — every `<cite/>` in the answer is validated against the
  database: non-existent articles, articles outside their temporal validity
  and repealed articles are flagged; citations of real articles that were
  *not* in the retrieved context (the most insidious hallucination) are
  reported as weak grounding. Case law is cited in prose with its real
  docket data, never invented.
- **Temporal validity** — every partition and chunk carries
  `effective_from`/`effective_to`; retrieval filters by validity date on all
  branches (default: today).
- **API & UI** — FastAPI with SSE streaming, token auth, rate limiting;
  Next.js chat with retrieved-sources panel and unverified-citation warnings.

## Quick start

Prerequisites: Docker, [`uv`](https://docs.astral.sh/uv/), `pnpm`, Node ≥ 20,
an OpenAI API key (default backend; local backends supported).

```bash
git clone <repo-url> caucus && cd caucus
cp .env.example .env          # then set OPENAI_API_KEY
make install                  # Python (uv) + Node (pnpm) deps
make up                       # Postgres :55432, Qdrant :6333, Redis, Langfuse
make migrate                  # DB schema
make seed-all                 # ingest all 50 sources (≈ cents of embeddings)
make dev                      # API :8000, web :3000
```

Optional:

```bash
uv run caucus-ingest ingest-eu --atto gdpr --from-fixture       # EU acts
uv run caucus-ingest ingest-cassazione --kind snpen --max 2000  # case law
make eval                     # run Caucus Bench against your instance
```

## Architecture (short)

```
apps/web              Next.js 15 chat UI
apps/api              FastAPI — chat SSE, search, citation validator
services/rag-core     retriever, rerankers, query expansion, act registry, schemas
services/ingestion    Normattiva AKN parser, EUR-Lex parser, Cassazione harvester,
                      legal-aware chunker (contextual headers), loaders
benchmark/            Caucus Bench: gold set + harness (MIT)
```

Design notes live in [docs/](docs/); the honest gap analysis that drove the
current architecture is in [docs/AUDIT_SOTA_2026-07-31.md](docs/AUDIT_SOTA_2026-07-31.md).

## Data sources & licensing of data

Italian legislative texts are in the public domain (art. 5, L. 633/1941).
Normattiva and EUR-Lex are queried at conservative rate limits (≤1 req/s);
Cassazione decisions come from the public SentenzeWeb service in their
official anonymized form, harvested at 0.5 req/s. See
[data/fixtures/normattiva/README.md](data/fixtures/normattiva/README.md).
Note: the repo ships ~50 MB of official XML fixtures so parser tests are
reproducible offline.

## License

- **Application code**: [AGPL-3.0](LICENSE) — if you run a modified Caucus as
  a service, you share your changes.
- **Benchmark** (`benchmark/`): [MIT](benchmark/LICENSE) — evaluate anything
  against it, publish results freely.

## Status & roadmap

Working today: everything described above. Known limits (tracked honestly):
single-snapshot consolidation (no historical versioning yet), EU acts are the
OJ base text (not consolidated), conversation history is client-side, TTFT
~3-4s on conceptual questions. Roadmap: historical versioning via Normattiva
`dataVigenza`, self-hosted embeddings (BGE-M3 hybrid), structured citation
outputs, server-side conversations + audit log, agentic multi-hop research.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security reports:
[.github/SECURITY.md](.github/SECURITY.md).
