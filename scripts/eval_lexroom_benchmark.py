#!/usr/bin/env python3
"""Benchmark end-to-end Avvocato vs standard Lexroom (ricerca normativa).

Esegue per ogni caso gold:
  1. POST /api/v1/search  → recall@10 articoli attesi
  2. POST /api/v1/chat    → citazioni, grounding, keywords, latenza
  3. Scorecard aggregata con gap analysis vs Lexroom

Usage:
  uv run python scripts/eval_lexroom_benchmark.py
  uv run python scripts/eval_lexroom_benchmark.py --api http://localhost:8000 --json-out reports/eval.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = ROOT / "scripts" / "eval_gold_cases.json"

CITE_TAG = re.compile(
    r'<cite\s+source="([a-z0-9-]+)"\s+part="[a-z]+"\s+num="([^"]+)"',
    re.I,
)
FREEFORM = re.compile(
    r"\bart(?:icolo)?\.?\s+"
    r"([0-9]+(?:[-\s]?(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?)"
    r".*?"
    r"(c\.?\s*c\.?|c\.?\s*p\.?)",
    re.I,
)


@dataclass
class CaseResult:
    case_id: str
    category: str
    question: str
    passed: bool
    score: float
    max_score: float
    checks: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    retrieval_ms: int | None = None
    chat_ms: int | None = None
    answer_preview: str = ""
    lexroom_note: str | None = None


@dataclass
class BenchmarkReport:
    api: str
    timestamp: str
    stack_ready: bool
    corpus: dict[str, Any]
    cases: list[CaseResult]
    summary: dict[str, Any]
    lexroom_comparison: dict[str, Any]


def _cite_key(source: str, num: str) -> tuple[str, str]:
    n = re.sub(r"\s+", "-", num.strip()).lower()
    return source.lower(), n


def _extract_citations(text: str) -> set[tuple[str, str]]:
    cites: set[tuple[str, str]] = set()
    for s, n in CITE_TAG.findall(text):
        cites.add(_cite_key(s, n))
    for m in FREEFORM.finditer(text):
        suffix = m.group(2).lower().replace(".", "").replace(" ", "")
        src = "cc" if "cc" in suffix else "cp" if "cp" in suffix else suffix
        cites.add(_cite_key(src, m.group(1)))
    return cites


def _hits_contain(hits: list[dict], expected: dict[str, str]) -> bool:
    want = _cite_key(expected["source"], expected["num"])
    for h in hits:
        c = h.get("citation") or {}
        if c:
            got = _cite_key(c.get("source", ""), c.get("num", ""))
            if got == want:
                return True
        disp = (h.get("citation_display") or "").lower()
        if f"art. {expected['num']}" in disp or f"art.{expected['num']}" in disp:
            return True
    return False


def _score_case(case: dict, search: dict, chat: dict) -> CaseResult:
    max_score = 0.0
    score = 0.0
    checks: dict[str, Any] = {}
    failures: list[str] = []

    hits = search.get("hits") or []
    answer = chat.get("answer") or ""
    invalid_cites = chat.get("invalid_citations") or []
    retrieval_ms = search.get("latency_ms")
    chat_ms = chat.get("latency_ms")

    optional = case.get("optional", False)

    # --- Retrieval recall (30 pts) ---
    max_score += 30
    must = case.get("must_retrieve") or []
    must_any = case.get("must_retrieve_any") or []
    if must:
        found = [e for e in must if _hits_contain(hits, e)]
        recall = len(found) / len(must)
        checks["retrieval_recall"] = recall
        checks["retrieval_found"] = found
        checks["retrieval_missed"] = [e for e in must if e not in found]
        pts = 30 * recall
        score += pts
        if recall < 1.0:
            failures.append(f"retrieval: mancano {checks['retrieval_missed']}")
    elif must_any:
        ok = any(_hits_contain(hits, e) for e in must_any)
        checks["retrieval_any"] = ok
        if ok:
            score += 30
        else:
            failures.append(f"retrieval: nessuno tra {must_any}")
    else:
        score += 30
        checks["retrieval_skipped"] = True

    # --- Citation accuracy (25 pts) ---
    max_score += 25
    if invalid_cites:
        checks["invalid_citations"] = invalid_cites
        failures.append(f"allucinazioni: {len(invalid_cites)} citazioni invalide")
    else:
        score += 15
        checks["no_invalid_citations"] = True

    cites = _extract_citations(answer)
    checks["citations_in_answer"] = sorted(f"{s}:{n}" for s, n in cites)

    should = case.get("should_cite") or []
    should_any = case.get("should_cite_any") or []
    if should:
        cited_ok = all(_cite_key(e["source"], e["num"]) in cites for e in should)
        checks["should_cite_ok"] = cited_ok
        if cited_ok:
            score += 10
        else:
            failures.append(f"risposta non cita: {should}")
    elif should_any:
        cited_any = any(_cite_key(e["source"], e["num"]) in cites for e in should_any)
        checks["should_cite_any_ok"] = cited_any
        if cited_any:
            score += 10
        else:
            failures.append(f"risposta non cita nessuno tra {should_any}")
    elif not case.get("answer_should_admit_gap"):
        if cites:
            score += 10
        checks["has_citations"] = bool(cites)

    # --- Answer quality (25 pts) ---
    max_score += 25
    min_chars = case.get("min_answer_chars", 50)
    if len(answer) >= min_chars:
        score += 5
        checks["min_length_ok"] = True
    else:
        failures.append(f"risposta troppo corta ({len(answer)} < {min_chars})")

    kws = case.get("answer_keywords") or []
    kws_any = case.get("answer_keywords_any") or []
    if kws:
        missing = [k for k in kws if k.lower() not in answer.lower()]
        checks["keywords_missing"] = missing
        if not missing:
            score += 15
        else:
            score += max(0, 15 - 5 * len(missing))
            failures.append(f"keywords mancanti: {missing}")
    elif kws_any:
        if any(k.lower() in answer.lower() for k in kws_any):
            score += 15
            checks["keywords_any_ok"] = True
        else:
            failures.append(f"nessuna keyword tra {kws_any}")

    if case.get("answer_should_admit_gap"):
        gap_phrases = ["non trovo", "non ho trovato", "corpus", "indicizz", "giurisprudenz"]
        if any(p in answer.lower() for p in gap_phrases):
            score += 5
            checks["honest_gap_admission"] = True
        else:
            failures.append("doveva ammettere assenza giurisprudenza nel corpus")

    forbidden = case.get("forbidden_patterns") or []
    for pat in forbidden:
        if pat.lower() in answer.lower():
            failures.append(f"pattern vietato in risposta: {pat!r}")

    # --- Grounding (10 pts) ---
    max_score += 10
    retrieval_keys = set()
    for h in hits[:8]:
        c = h.get("citation") or {}
        if c.get("source") and c.get("num"):
            retrieval_keys.add(_cite_key(c["source"], c["num"]))
    grounded = [c for c in cites if c in retrieval_keys]
    checks["grounded_citations"] = sorted(f"{s}:{n}" for s, n in grounded)
    if cites:
        grounding_ratio = len(grounded) / len(cites)
        checks["grounding_ratio"] = grounding_ratio
        score += 10 * grounding_ratio
        if grounding_ratio < 0.8:
            failures.append(f"grounding basso: {grounding_ratio:.0%}")
    else:
        score += 5 if case.get("answer_should_admit_gap") else 0

    # --- Latency (10 pts) — Lexroom target P50 TTFT < 2s ---
    max_score += 10
    if chat_ms is not None:
        checks["chat_latency_ms"] = chat_ms
        if chat_ms <= 2000:
            score += 10
        elif chat_ms <= 5000:
            score += 7
        elif chat_ms <= 10000:
            score += 4
        else:
            failures.append(f"latenza alta: {chat_ms}ms")

    pct = 100 * score / max_score if max_score else 0
    passed = pct >= 70 and not invalid_cites and (optional or len(failures) <= 2)
    if optional and pct < 50:
        passed = True  # gap attesi, non penalizzano il core

    return CaseResult(
        case_id=case["id"],
        category=case["category"],
        question=case["question"],
        passed=passed,
        score=round(score, 1),
        max_score=max_score,
        checks=checks,
        failures=failures,
        retrieval_ms=retrieval_ms,
        chat_ms=chat_ms,
        answer_preview=answer[:400].replace("\n", " "),
        lexroom_note=case.get("lexroom_note") or case.get("lexroom_gap"),
    )


async def _check_stack(client: httpx.AsyncClient) -> tuple[bool, dict]:
    try:
        r = await client.get("/api/v1/health/ready", timeout=10)
        r.raise_for_status()
        data = r.json()
        ok = data.get("status") == "ok" and all(data.get("checks", {}).values())
        return ok, data
    except Exception as exc:
        return False, {"error": str(exc)}


async def _corpus_stats(client: httpx.AsyncClient, api: str) -> dict[str, Any]:
    del client
    import os

    stats: dict[str, Any] = {}
    try:
        import subprocess

        chunks = subprocess.check_output(
            [
                "psql",
                "-h",
                "localhost",
                "-p",
                "55432",
                "-U",
                "avvocato",
                "-d",
                "avvocato",
                "-tAX",
                "-c",
                "SELECT count(*) FROM norm_chunk",
            ],
            env={**os.environ, "PGPASSWORD": "avvocato"},
            text=True,
        ).strip()
        stats["postgres_chunks"] = int(chunks)
    except Exception as exc:
        stats["postgres_error"] = str(exc)

    try:
        q = httpx.get(
            "http://localhost:6333/collections/codici",
            headers={"api-key": "local-dev-key"},
            timeout=5,
        )
        if q.status_code == 200:
            stats["qdrant_points"] = q.json()["result"]["points_count"]
    except Exception as exc:
        stats["qdrant_error"] = str(exc)

    stats["api"] = api
    return stats


async def _search(client: httpx.AsyncClient, question: str) -> dict:
    t0 = time.perf_counter()
    r = await client.post(
        "/api/v1/search",
        json={
            "query": {
                "text": question,
                "corpora": ["codici"],
                "top_k_retrieve": 20,
                "top_k_rerank": 10,
            }
        },
        timeout=120,
    )
    r.raise_for_status()
    body = r.json()["result"]
    ms = int((time.perf_counter() - t0) * 1000)
    hits = []
    for h in body.get("hits") or []:
        c = h.get("citation")
        if isinstance(c, dict):
            cite = {
                "source": c.get("source"),
                "num": c.get("num"),
                "comma": c.get("comma"),
            }
            disp = None
            if c.get("source") and c.get("num"):
                suffix = {"cc": "c.c.", "cp": "c.p."}.get(c["source"], c["source"])
                disp = (
                    f"art. {c['num']}"
                    + (f", c. {c['comma']}" if c.get("comma") else "")
                    + f" {suffix}"
                )
        else:
            cite = None
            disp = None
        hits.append(
            {
                "citation": cite,
                "citation_display": disp,
                "score": h.get("score_final"),
                "text": (h.get("text") or "")[:120],
            }
        )
    return {"hits": hits, "latency_ms": body.get("latency_ms") or ms}


async def _chat(client: httpx.AsyncClient, question: str) -> dict:
    t0 = time.perf_counter()
    answer = ""
    hits: list = []
    invalid: list = []
    error = None

    async with client.stream(
        "POST",
        "/api/v1/chat",
        json={"question": question, "corpora": ["codici"]},
        timeout=180,
    ) as resp:
        resp.raise_for_status()
        event = None
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event:
                payload = json.loads(line.split(":", 1)[1])
                if event == "retrieval":
                    hits = payload.get("hits") or []
                elif event == "token":
                    answer += payload.get("text") or ""
                elif event == "citation_warnings":
                    invalid = payload.get("invalid") or []
                elif event == "error":
                    error = payload.get("message")

    ms = int((time.perf_counter() - t0) * 1000)
    return {
        "answer": answer,
        "invalid_citations": invalid,
        "error": error,
        "latency_ms": ms,
        "retrieval_hits": hits,
    }


def _lexroom_comparison(results: list[CaseResult], corpus: dict) -> dict[str, Any]:
    core = [r for r in results if r.category not in ("giurisprudenza",) and "gap" not in r.case_id]
    optional = [r for r in results if r not in core]

    core_pct = sum(r.score / r.max_score for r in core) / len(core) * 100 if core else 0
    cite_clean = sum(1 for r in core if not (r.checks.get("invalid_citations")))
    latencies = [r.chat_ms for r in core if r.chat_ms]

    return {
        "avvocato_core_score_pct": round(core_pct, 1),
        "lexroom_equivalent_dimensions": {
            "retrieval_su_corpus_verificato": {
                "avvocato": round(
                    100
                    * sum(1 for r in core if not r.checks.get("retrieval_missed"))
                    / max(len(core), 1),
                    1,
                ),
                "lexroom_claim": "~95%+ su fonti indicizzate",
                "verdict": "pari" if core_pct >= 75 else "sotto",
            },
            "citazioni_verificabili": {
                "avvocato": f"{cite_clean}/{len(core)} casi senza allucinazioni",
                "lexroom_claim": "zero allucinazioni, link fonte ufficiale",
                "verdict": "pari" if cite_clean == len(core) else "sotto",
            },
            "copertura_fonti": {
                "avvocato": f"CC+CP indicizzati ({corpus.get('postgres_chunks', '?')} chunk)",
                "lexroom": "codici + leggi + Cassazione + prassi + circolari",
                "verdict": "sotto (gap atteso fase 1)",
            },
            "giurisprudenza": {
                "avvocato": "non disponibile",
                "lexroom": "sentenze integrali + massime",
                "verdict": "sotto",
            },
            "analisi_documenti_word": {
                "avvocato": "non disponibile",
                "lexroom": "upload + Word add-in",
                "verdict": "sotto",
            },
            "latenza_p50_ms": {
                "avvocato": sorted(latencies)[len(latencies) // 2] if latencies else None,
                "lexroom_target": "< 2000ms TTFT",
            },
        },
        "overall_vs_lexroom": (
            "COMPETITIVO su Q&A codici (CC/CP) se score core ≥ 75% e zero allucinazioni"
            if core_pct >= 75 and cite_clean == len(core)
            else "SOTTO Lexroom — migliorare retrieval/citazioni prima del GA"
        ),
        "optional_gap_cases": [
            {
                "id": r.case_id,
                "score_pct": round(100 * r.score / r.max_score, 1),
                "note": r.lexroom_note,
            }
            for r in optional
        ],
    }


async def run_benchmark(api: str, gold_path: Path) -> BenchmarkReport:
    gold = json.loads(gold_path.read_text())
    cases = gold["cases"]

    async with httpx.AsyncClient(base_url=api) as client:
        ready, health = await _check_stack(client)
        corpus = await _corpus_stats(client, api)

        results: list[CaseResult] = []
        if not ready:
            for c in cases:
                results.append(
                    CaseResult(
                        case_id=c["id"],
                        category=c["category"],
                        question=c["question"],
                        passed=False,
                        score=0,
                        max_score=100,
                        failures=[f"stack non pronto: {health}"],
                    )
                )
        else:
            for i, case in enumerate(cases, 1):
                print(f"[{i}/{len(cases)}] {case['id']}...", flush=True)
                try:
                    search = await _search(client, case["question"])
                    chat = await _chat(client, case["question"])
                    if not search.get("hits") and chat.get("retrieval_hits"):
                        search["hits"] = [
                            {
                                "citation": None,
                                "citation_display": h.get("citation_display"),
                                "score": h.get("score"),
                                "text": h.get("excerpt", ""),
                            }
                            for h in chat["retrieval_hits"]
                        ]
                    cr = _score_case(case, search, chat)
                    results.append(cr)
                    status = "PASS" if cr.passed else "FAIL"
                    print(
                        f"  {status} {cr.score}/{cr.max_score} "
                        f"ret={cr.retrieval_ms}ms chat={cr.chat_ms}ms",
                        flush=True,
                    )
                except Exception as exc:
                    results.append(
                        CaseResult(
                            case_id=case["id"],
                            category=case["category"],
                            question=case["question"],
                            passed=False,
                            score=0,
                            max_score=100,
                            failures=[str(exc)],
                        )
                    )
                    print(f"  ERROR {exc}", flush=True)

    core = [r for r in results if r.category not in ("giurisprudenza",) and "gap" not in r.case_id]
    optional = [r for r in results if r not in core]
    summary = {
        "total": len(results),
        "core_passed": sum(1 for r in core if r.passed),
        "core_total": len(core),
        "core_avg_score_pct": round(
            100 * sum(r.score / r.max_score for r in core) / max(len(core), 1), 1
        ),
        "hallucination_cases": sum(1 for r in results if r.checks.get("invalid_citations")),
        "avg_chat_latency_ms": round(sum(r.chat_ms or 0 for r in core) / max(len(core), 1)),
        "optional_passed": sum(1 for r in optional if r.passed),
    }
    comparison = _lexroom_comparison(results, corpus)

    return BenchmarkReport(
        api=api,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        stack_ready=ready,
        corpus=corpus,
        cases=results,
        summary=summary,
        lexroom_comparison=comparison,
    )


def _print_report(report: BenchmarkReport) -> None:
    print("\n" + "=" * 72)
    print("BENCHMARK AVVOCATO vs STANDARD LEXROOM")
    print("=" * 72)
    print(f"API: {report.api}  ready={report.stack_ready}")
    print(f"Corpus: {report.corpus}")
    print(f"\nSummary: {json.dumps(report.summary, indent=2)}")
    print("\n--- Confronto Lexroom ---")
    print(json.dumps(report.lexroom_comparison, indent=2, ensure_ascii=False))

    print("\n--- Dettaglio casi falliti ---")
    for c in report.cases:
        if not c.passed:
            print(f"\n✗ {c.case_id} ({c.score}/{c.max_score})")
            for f in c.failures:
                print(f"    - {f}")
            if c.answer_preview:
                print(f"    preview: {c.answer_preview[:200]}...")

    print("\n--- Scoreboard ---")
    for c in report.cases:
        mark = "✓" if c.passed else "✗"
        pct = 100 * c.score / c.max_score if c.max_score else 0
        print(f"  {mark} {c.case_id:30s} {pct:5.1f}%  chat={c.chat_ms}ms")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    report = asyncio.run(run_benchmark(args.api, args.gold))
    _print_report(report)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {
                    "api": report.api,
                    "timestamp": report.timestamp,
                    "stack_ready": report.stack_ready,
                    "corpus": report.corpus,
                    "summary": report.summary,
                    "lexroom_comparison": report.lexroom_comparison,
                    "cases": [asdict(c) for c in report.cases],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print(f"\nReport JSON: {args.json_out}")

    if not report.stack_ready:
        return 2
    if report.summary["core_avg_score_pct"] < 70:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
