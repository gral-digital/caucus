# Caucus Bench — Results

Leaderboard of systems evaluated on Caucus Bench. To submit: open a PR adding
a row **plus** the raw JSON report, the exact configuration, and the gold set
version used. Results on a modified gold set are not comparable and will not
be accepted. Latency figures must state the hardware and whether the machine
was otherwise idle.

| System | Date | Gold set | Pass | Pass (hard) | Recall@8 | MRR | Cite recall | Halluc. | Refusal | Over-refusal | Gap adm. | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Caucus reference** (gpt-4o + gpt-4o structured expansion + text-embedding-3-small + bge-reranker-v2-m3 local) | 2026-07-31 | v2.3 | **96%** | 95% | **97%** | 0.87 | 97% | **0.0%** | 100% | **0%** | 100% | corpus: 50 Normattiva + 14 EU + 50k Cassazione; Apple M-series (MPS, **not idle**: harvest attivo); TTFT p50 8.7s / p95 23s; 0 errors / 171 |
| Caucus (previous, keyword-reranker fallback) | 2026-07-31 | v2.3 | 85% | 78% | 85% | 0.74 | 90% | 0.0% | 100% | 0% | 100% | superseded — vedi correzione sotto |

> **Reading the numbers honestly.**
> - **Correction**: the previous 85% row was labelled "bge-reranker-v2-m3
>   local" but actually ran on the keyword fallback — `sentence-transformers`
>   was missing from the venv and the factory degraded silently (now it warns,
>   and the extra is installed by default). Part of the recall drop attributed
>   to case-law growth was this.
> - The jump to 96/97 comes from three measured changes: structured query
>   expansion (the expansion model returns up to 6 candidate articles as
>   `sigla numero`, validated against the source catalog, merged as non-pinned
>   lookups), the restored cross-encoder, and a citation-repair pass when
>   post-generation validation finds non-existent references.
> - **Run-to-run variance is real**: across 4 runs of the same configuration,
>   pass ranged 95.3–95.9% and recall@8 96.2–97.5% (OpenAI nondeterminism in
>   expansion and generation). We report the last full run, not the best one.
> - **Latency regressed by design**: expansion moved from gpt-4o-mini to
>   gpt-4o (~+1.5s, measured 8/14 vs 5/14 expected articles on the hardest
>   cases) and the repair pass adds one LLM call when a citation is invalid.
>   TTFT p50 was also measured while the Cassazione harvest was indexing in
>   background; on an idle machine earlier runs measured p50 ~6.1s. A latency
>   pass (streaming expansion, smaller candidate budget) is open work.

## Reproduction

```bash
make up && make migrate && make seed-all      # corpus
make dev-api                                   # or: make dev
make eval                                      # writes reports/eval_v2_latest.json
# report canonici della sessione: reports/eval_{BASELINE,MILESTONE,CURRENT}_*.json
```

## History

- **v2.3 rerun** (2026-07-31, sera): structured expansion + cross-encoder
  restored + citation repair — pass 96%, recall@8 97%, hallucination 0%.
  Canonical report: `reports/eval_CURRENT_gold-v2.3_espansione-strutturata_*.json`.
- **v2.3** (2026-07-31): added the `professional-legitimate` class with
  `expect_no_refusal` (over-refusal metric) and two adversarial cases probing
  a professional framing.
- **v2.2** (2026-07-31): `gap-cassazione` updated after real case law entered
  the corpus; +15 cases for EU/compliance sources added in v2.1.
- **v2.0** (2026-07-31): initial public gold set — 148 cases.
