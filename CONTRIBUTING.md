# Contributing to Caucus

Grazie! / Thank you! Contributions are welcome in **Italian or English**.

## Ground rules

1. **Correctness over features.** This is legal software: a wrong answer
   presented confidently causes real harm. Every change touching parsing,
   retrieval, citation validation or temporal validity needs tests.
2. **The benchmark is the referee.** Changes claiming quality improvements
   must include a Caucus Bench run (`make eval`) before/after, with the JSON
   reports. The gold set (`benchmark/gold_cases.json`) may only change with an
   explicit motivation in the commit message — never to fit a system's output.
3. **Honest docs.** Don't document aspirations as features. If something is a
   stub, say so.

## Dev setup

```bash
cp .env.example .env   # set OPENAI_API_KEY
make install && make up && make migrate && make seed-all-fast
```

`seed-all-fast` ingests Postgres-only (no embedding costs) — enough for
parser/loader/API work. Use `make seed-all` for retrieval work.

## Quality gates (all blocking in CI)

```bash
make lint        # ruff check + format, eslint
make typecheck   # mypy strict on src, tsc
make test        # pytest (Python), turbo test (Node)
```

- Python: ruff + mypy `strict` on all `src/` trees. Type your code.
- Tests live next to each package (`services/*/tests`, `apps/api/tests`).
- Comments explain *why*, in Italian or English — pick one per file and be
  consistent with what's there.

## Adding a legal source

- **Normattiva**: add an entry to `CODICI_CATALOG`
  (`services/ingestion/src/avvocato_ingestion/parsers/normattiva_akn.py`) with
  the correct URN, plus display suffixes in `schemas/citation.py` and
  `loader.py`, and the act registry is regenerated from URNs. Fetch a fixture,
  check article count and rubrica coverage, add a benchmark case.
- **EUR-Lex**: add to `EURLEX_CATALOG` (`fetchers/eurlex.py`) with the CELEX
  number; verify the parser extracts the expected article count.
- Always run the parser validation before ingesting: article counts, duplicate
  numbers, rubrica coverage.

## Scrapers etiquette

Public portals are queried at conservative rate limits (Normattiva/EUR-Lex
≤ 1 req/s, SentenzeWeb 0.5 req/s). Do not raise them. Do not remove the
oscuramento filter on Cassazione decisions.

## PR checklist

- [ ] Tests added/updated and green
- [ ] `make lint typecheck` clean
- [ ] Benchmark run attached if quality-relevant
- [ ] Docs updated if behaviour changed
- [ ] No secrets, no `.env`, no large binaries
