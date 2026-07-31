# Caucus Bench — Results

Leaderboard of systems evaluated on Caucus Bench. To submit: open a PR adding
a row **plus** the raw JSON report, the exact configuration, and the gold set
version used. Results on a modified gold set are not comparable and will not
be accepted. Latency figures must state the hardware and whether the machine
was otherwise idle.

| System | Date | Gold set | Pass | Pass (hard) | Recall@8 | MRR | Cite recall | Halluc. | Refusal | Over-refusal | Gap adm. | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Caucus reference** (gpt-4o + gpt-4o-mini expansion + text-embedding-3-small + bge-reranker-v2-m3 local) | 2026-07-31 | v2.3 | 85% | 78% | 85% | 0.74 | 90% | **0.0%** | 100% | **0%** | 100% | corpus: 50 Normattiva + 14 EU + 50k Cassazione; Apple M-series (MPS); TTFT p50 2216ms; 0 errors / 171 |

> **Reading the numbers honestly.** Recall dropped from 92% to 85% when the
> case-law corpus grew from 24k to 50k decisions: a larger secondary corpus
> competes for candidate slots. Mitigated with a per-corpus quota and
> proportional fusion (see `HybridRetriever`), but not fully recovered — the
> remaining failures are conceptual queries whose expansion does not surface
> the right article number. This is documented rather than hidden: it is
> exactly the kind of regression a benchmark exists to reveal.

## Reproduction

```bash
make up && make migrate && make seed-all      # corpus
make dev-api                                   # or: make dev
make eval                                      # writes reports/eval_v2_latest.json
# report canonici della sessione: reports/eval_{BASELINE,MILESTONE,CURRENT}_*.json
```

## History

- **v2.3** (2026-07-31): added the `professional-legitimate` class with
  `expect_no_refusal` (over-refusal metric) and two adversarial cases probing
  a professional framing.
- **v2.2** (2026-07-31): `gap-cassazione` updated after real case law entered
  the corpus; +15 cases for EU/compliance sources added in v2.1.
- **v2.0** (2026-07-31): initial public gold set — 148 cases.
