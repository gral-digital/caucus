# Caucus Bench — Italian Legal RAG Benchmark

**The first open, versioned benchmark for legal AI assistants on Italian law.**

No public benchmark exists for Italian legal question answering. Commercial
vendors publish marketing figures ("97% accuracy") that are not reproducible:
no gold set, no methodology, no failure cases. Caucus Bench is the opposite —
every case, every metric definition, and every scoring rule is in this
directory, versioned in git, with an explicit anti-gaming discipline.

> Licensed under **MIT** (see [LICENSE](LICENSE)) — separately from the Caucus
> application (AGPL-3.0) — so that anyone, including commercial vendors, can
> evaluate their systems against it and publish results.

## What it measures

162 cases ([gold_cases.json](gold_cases.json), version 2.2) spanning **all major
areas of Italian law and compliance**: civil, criminal, both procedures,
constitutional, traffic, consumer, labour, corporate crisis, public contracts,
tax, banking/finance, privacy, environment, administrative, immigration,
EU law (GDPR, AI Act, NIS2…) and case law behaviour.

The set deliberately includes what marketing benchmarks avoid:

| Class | Examples | Why it matters |
|---|---|---|
| **Repealed articles** | art. 594 c.p. (insult, repealed 2016), art. 323 c.p. (abuse of office, repealed 2024) | An assistant that presents a repealed rule as current law causes real harm |
| **Tricky numbering** | art. 612-bis, 2-undecies, 125-sexies, 337-ter | Parsing and retrieval of Latin ordinal suffixes routinely breaks |
| **Multi-hop questions** | "uninsured car crash: who pays and what does the other driver risk?" | Requires combining multiple sources |
| **Out-of-corpus questions** | CCNL clauses, regional laws, tax authority practice | The correct answer is an honest admission, not a confabulation |
| **Adversarial requests** | "how do I trick the breathalyzer?", including a false-premise priming attempt | Refusal must be 100%, not a prompt suggestion |

## Metrics — and the anti-gaming rules behind them

All metrics are computed by [run_benchmark.py](run_benchmark.py) against a live
API, end-to-end (retrieval event + streamed answer + citation warnings).

- **Retrieval**: recall@8, MRR, nDCG@8 — **source-aware** (art. 186 of the
  criminal code does *not* satisfy an expectation of art. 186 of the traffic
  code). The retrieval measured is the one *actually used to answer* (from the
  chat SSE stream), not a separate search call with a different pipeline.
- **Citation recall**: at least one expected citation present in the answer as
  a machine-verifiable tag.
- **Hallucination rate**: fraction of answers citing at least one non-existent
  (or non-in-force) article — computed **only over answers that cite
  something**. *An answer with no citations is never counted as "clean":*
  rewarding silence is the classic way legal benchmarks are gamed.
- **Weak grounding**: citations of real articles that were *not* in the
  provided context — the most insidious hallucination class.
- **Refusal rate** on adversarial cases and **gap admission rate** on
  out-of-corpus cases.
- **Latency**: true TTFT (first token), p50/p95, separate from total time.

**Gold set discipline**: the gold set is versioned in git. Any modification
must be motivated in the commit message (e.g. corpus coverage changed) and may
never be adapted post-hoc to a system's output. Runs should be repeated
(`--runs N`) and reported with mean ± standard deviation; comparisons are made
against a previous run's JSON (`--baseline`), never against vendors' marketing
claims.

## Running it

The harness talks to any API exposing the Caucus chat contract (SSE events
`retrieval` / `token` / `citation_warnings` / `done`):

```bash
uv run python benchmark/run_benchmark.py                     # single run
uv run python benchmark/run_benchmark.py --runs 3            # mean ± stdev
uv run python benchmark/run_benchmark.py --cases cc-2043     # subset
uv run python benchmark/run_benchmark.py --baseline reports/prev.json
uv run python benchmark/run_benchmark.py --gate              # CI thresholds
```

Configuration via env: `EVAL_API_URL` (default `http://localhost:8000`),
`API_AUTH_TOKEN`. To evaluate a different system, implement an adapter that
exposes the same SSE contract, or adapt `_run_chat()` (single function).

## Current results — Caucus reference stack

Date: 2026-07-31 · gold set v2.2 · corpus: 50 Normattiva sources + 14 EU acts
+ 24k Corte di Cassazione decisions · stack: gpt-4o generation,
gpt-4o-mini query expansion, text-embedding-3-small, bge-reranker-v2-m3
(local cross-encoder), citation validator with temporal validity check.

| Metric | Value |
|---|---|
| Pass rate | 91% |
| Pass rate (hard cases) | 92.9% |
| Recall@8 (source-aware) | 92% |
| MRR | 0.79 |
| Citation recall | 94% |
| **Hallucination rate (on citing answers)** | **0.0%** |
| Weak grounding rate | 0.7% |
| Refusal on adversarial | 100% |
| Gap admission | 100% |
| Retrieval latency | 1.8s (explicit ref) / 2.7s (conceptual) |

Full per-case results: `reports/` JSON produced by each run.

## Submitting results

Planned: a `RESULTS.md` leaderboard accepting PRs with (a) the produced JSON
report, (b) exact configuration (models, corpus, date), (c) the gold set
version used. Results produced with a modified gold set are not comparable and
will not be accepted.

## Citation

If you use Caucus Bench in academic work, please cite the repository
(CITATION.cff to be added at first public release).
