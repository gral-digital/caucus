"""Test delle funzioni pure dell'harness eval v2 (metriche di ranking, parsing)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("eval_v2", REPO_ROOT / "scripts" / "eval_v2.py")
assert _spec is not None and _spec.loader is not None
eval_v2 = importlib.util.module_from_spec(_spec)
# I dataclass con `from __future__ import annotations` richiedono il modulo
# registrato in sys.modules per risolvere le annotazioni.
sys.modules["eval_v2"] = eval_v2
_spec.loader.exec_module(eval_v2)


def test_gold_set_is_valid_and_large_enough():
    gold = json.loads((REPO_ROOT / "scripts" / "eval_gold_v2.json").read_text())
    cases = gold["cases"]
    assert len(cases) >= 100
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "id duplicati nel gold set"
    for c in cases:
        assert c.get("question"), f"caso senza domanda: {c['id']}"
        # Ogni caso deve avere ALMENO un criterio verificabile
        assert any(
            k in c
            for k in (
                "must_retrieve",
                "must_retrieve_any",
                "should_cite_any",
                "keywords_groups",
                "expect_refusal",
                "expect_gap_admission",
            )
        ), f"caso senza criteri: {c['id']}"


def test_ranking_metrics_source_aware():
    """Un art. 186 c.p. NON soddisfa l'attesa art. 186 CdS."""
    expected = [("cds", "186")]
    ranked = [("cp", "186"), ("cds", "186")]
    recall, mrr, _ndcg = eval_v2._ranking_metrics(expected, any_mode=False, ranked=ranked)
    assert recall == 1.0
    assert mrr == 0.5  # primo rilevante in posizione 2
    ranked_wrong = [("cp", "186")]
    recall, mrr, _ = eval_v2._ranking_metrics(expected, any_mode=False, ranked=ranked_wrong)
    assert recall == 0.0
    assert mrr == 0.0


def test_ranking_metrics_perfect_first_hit():
    recall, mrr, ndcg = eval_v2._ranking_metrics(
        [("cc", "2043")], any_mode=False, ranked=[("cc", "2043"), ("cc", "1218")]
    )
    assert (recall, mrr, ndcg) == (1.0, 1.0, 1.0)


def test_ranking_metrics_any_mode():
    expected = [("cp", "42"), ("cp", "43")]
    recall, _, _ = eval_v2._ranking_metrics(expected, any_mode=True, ranked=[("cp", "43")])
    assert recall == 1.0


def test_extract_citations_from_tags():
    text = 'Vedi <cite source="cp" part="articolo" num="575"/> e testo libero art. 640 c.p.'
    cited = eval_v2._extract_citations(text)
    # Solo i tag canonici contano: la prosa è già promossa a tag dal backend
    assert ("cp", "575") in cited
    assert ("cp", "640") not in cited


def test_hit_keys_parse_anchor():
    hits = [
        {"citation_anchor": "cc/art/2043"},
        {"citation_anchor": "cp/art/612-bis#c1"},
        {"citation_anchor": None},
    ]
    assert eval_v2._hit_keys(hits) == [("cc", "2043"), ("cp", "612-bis"), ("", "")]
