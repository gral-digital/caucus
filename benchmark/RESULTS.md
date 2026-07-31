# Caucus Bench — Results

Leaderboard of systems evaluated on Caucus Bench. To submit: open a PR adding
a row **plus** the raw JSON report, the exact configuration, and the gold set
version used. Results on a modified gold set are not comparable and will not
be accepted. Latency figures must state the hardware and whether the machine
was otherwise idle.

| System | Date | Gold set | Pass | Pass (hard) | Recall@8 | MRR | Cite recall | Halluc. | Refusal | Gap adm. | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Caucus reference** (gpt-4o + gpt-4o-mini expansion + text-embedding-3-small + bge-reranker-v2-m3 local) | 2026-07-31 | v2.2 | 91% | 92.9% | 92.1% | 0.787 | 94.0% | **0.0%** | 100% | 100%* | corpus: 50 Normattiva + 14 EU + 50k Cassazione; Apple M-series (MPS); single run, 1 transient network error / 162 |

\* gap admission 100% measured in the v2.2 run with concurrent ingestion load
(quality metrics unaffected, latency figures excluded for that run — see
`reports/eval_v2_sota2.json` for the clean-latency run: TTFT p50 6.5s with the
pre-optimization pipeline; current pipeline measures 1.8–2.7s retrieval).

## Reproduction

```bash
make up && make migrate && make seed-all      # corpus
make dev-api                                   # or: make dev
make eval                                      # writes reports/eval_v2_latest.json
```

## History

- **v2.2** (2026-07-31): `gap-cassazione` updated after real case law entered
  the corpus; +15 cases for EU/compliance sources added in v2.1.
- **v2.0** (2026-07-31): initial public gold set — 148 cases.
