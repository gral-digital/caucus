# Caucus

[![CI](https://github.com/gral-digital/caucus/actions/workflows/ci.yml/badge.svg)](https://github.com/gral-digital/caucus/actions/workflows/ci.yml)

**Open-source legal & compliance AI for Italian law, with a verifiable trust
layer and the first open Italian legal benchmark.**

*[Versione italiana → README.md](README.md)*

Caucus is a retrieval-augmented legal assistant over the Italian legal system:
50 consolidated statutes from Normattiva (civil, criminal and procedure codes,
consolidated acts, compliance legislation), 14 EU acts in Italian (GDPR,
AI Act, NIS2, DORA, MiCA and more), plus the full-text, anonymized decisions
of the Corte di Cassazione. Every normative citation in every answer is
validated post-generation against the corpus (existence, source, temporal
validity) and flagged to the user when it isn't verifiable.

> ⚠️ **Caucus is not a lawyer and its output is not legal advice.** It is a
> research and drafting aid. No professional relationship is created by using
> it. For decisions with legal consequences, consult a licensed professional.

## Why it exists

Legal AI vendors claim accuracy figures that cannot be reproduced. Caucus takes
the opposite bet: **open code (AGPL-3.0), open benchmark (MIT), honest
numbers**. [Caucus Bench](benchmark/README.md) has 171 cases across all major
areas of Italian law, including repealed articles, adversarial requests and
out-of-corpus questions. The reference stack currently measures:

| | |
|---|---|
| Pass rate | **98%** (100% on hard cases) |
| Source-aware recall@8 / MRR | **99% / 0.86** |
| Citation recall | **99%** |
| **Hallucinated citations** (over citing answers) | **0.0%** |
| Refusal on adversarial requests | **100%** |
| **Over-refusal on legitimate professional questions** | **0%** |

Run-to-run variance of the same configuration is real (pass 95–98%,
recall@8 96–99%, OpenAI nondeterminism): treat the range, not the peak, as
the honest number. Numbers, methodology and anti-gaming rules:
[benchmark/](benchmark/README.md).

## What's inside

- **Corpus**: 50 Normattiva sources parsed from official Akoma Ntoso XML
  (with repeal detection and consolidation dating), 14 EUR-Lex acts in
  Italian, incremental idempotent harvest of Cassazione decisions
  (~430k available, resumable).
- **Retrieval**: four fused branches (weighted RRF), namely deterministic
  article lookup, LLM query expansion with official-reference resolution
  ("art. 17 D.Lgs. 81/2008" → TU Sicurezza), Postgres FTS (Italian config)
  and dense vectors (Qdrant). Cross-encoder reranking (bge-reranker-v2-m3,
  local, MPS/CUDA/CPU). One-hop expansion over the **norm citation graph**
  extracted from the XML cross-references.
- **Trust layer**: every `<cite/>` in the answer is validated against the
  database. Non-existent articles, articles outside their temporal validity
  and repealed articles are flagged; citations of real articles that were
  *not* in the retrieved context (the most insidious hallucination) are
  reported as weak grounding. Case law is cited in prose with its real
  docket data, never invented.
- **Temporal validity**: every partition and chunk carries
  `effective_from`/`effective_to`; retrieval filters by validity date on all
  branches (default: today).
- **API & UI**: FastAPI with SSE streaming, token auth, rate limiting;
  Next.js chat with retrieved-sources panel and unverified-citation warnings.

## Quick start

Prerequisites: Docker, [`uv`](https://docs.astral.sh/uv/), `pnpm`, Node ≥ 20,
an OpenAI API key (default backend; local backends supported).

```bash
git clone https://github.com/gral-digital/caucus && cd caucus
cp .env.example .env          # then set OPENAI_API_KEY
make install                  # Python (uv) + Node (pnpm) deps
make up                       # Postgres :55432, Qdrant :6333, Redis, Langfuse
make migrate                  # DB schema
make corpus-import SRC=https://github.com/gral-digital/caucus/releases/download/corpus-20260801
make dev                      # API :8000, web :3000
```

**The corpus package** (published with releases) restores the whole indexed
corpus in one command, Postgres tables and Qdrant vectors included: no
ingestion run, no embedding cost. Checksums and schema revision are verified
before anything is written. To rebuild from public sources instead:

```bash
make seed-all                 # 50 Normattiva sources + EU acts (≈ cents of embeddings)
make harvest-cassazione       # case law, incremental and resumable
make eval                     # run Caucus Bench against your instance
```

Detailed guides (self-hosting, corpus, trust layer, API, benchmark) ship in
the app itself at `/docs`.

## Licensing

- **Application code**: [AGPL-3.0](LICENSE). Anyone offering a modified
  Caucus as a service shares their changes.
- **Benchmark** (`benchmark/`): [MIT](benchmark/LICENSE). Anyone can evaluate
  any system on it and publish results.

Note: the repo ships ~50 MB of official XML fixtures so parser tests are
reproducible offline.

## Status and roadmap

Working today: everything above. Known limits (tracked honestly):
single-snapshot consolidation (no historical versioning), EU acts in base GU
text (not consolidated), client-side conversation history, TTFT ~3-4s on
conceptual questions. Roadmap: historical multi-validity via Normattiva
`dataVigenza`, self-hosted embeddings (hybrid BGE-M3), structured-output
citations, server-side conversations and audit log, multi-hop agentic search.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security reports:
[.github/SECURITY.md](.github/SECURITY.md).
