"""Test della policy di guardrail nel system prompt.

Il prompt è l'unico livello che distingue difesa legittima da assistenza a
delinquere: un test che ne blinda le parti sostanziali evita che una
riscrittura reintroduca l'over-refusal (o, peggio, tolga il rifiuto).
"""

from __future__ import annotations

import json
from pathlib import Path

from caucus_api.services.chat_service import SYSTEM_PROMPT

REPO_ROOT = Path(__file__).resolve().parents[3]

# Il prompt è a capo fisso: normalizziamo gli spazi per cercare le frasi.
PROMPT = " ".join(SYSTEM_PROMPT.split())


def test_prompt_authorizes_full_defense():
    """Le attività difensive legittime devono essere esplicitamente autorizzate."""
    for expected in (
        "elementi costitutivi",
        "già poste in essere",
        "confine tra lecito e illecito",
        "riti alternativi",
        "diritto costituzionale",
    ):
        assert expected in PROMPT, f"il prompt non autorizza più: {expected!r}"


def test_prompt_still_refuses_operational_assistance():
    """Il rifiuto dell'assistenza operativa a un illecito resta, per chiunque chieda."""
    for expected in (
        "subornare testimoni",
        "distruggere prove",
        "anche un avvocato",
        "378",  # favoreggiamento
    ):
        assert expected in PROMPT, f"il prompt non rifiuta più: {expected!r}"


def test_prompt_asks_when_ambiguous():
    """Nel dubbio il modello deve chiedere a che punto sono i fatti."""
    assert "già accaduti" in PROMPT and "da compiere" in PROMPT


def test_gold_set_covers_both_directions():
    """Il benchmark misura sia il rifiuto dovuto sia il rifiuto indebito."""
    gold = json.loads((REPO_ROOT / "benchmark" / "gold_cases.json").read_text())
    refusal = [c for c in gold["cases"] if c.get("expect_refusal")]
    no_refusal = [c for c in gold["cases"] if c.get("expect_no_refusal")]
    assert len(refusal) >= 5, "troppi pochi casi adversarial"
    assert len(no_refusal) >= 5, "troppi pochi casi professionali legittimi"
    # Un caso non può attendersi entrambe le cose
    ids_r = {c["id"] for c in refusal}
    ids_n = {c["id"] for c in no_refusal}
    assert not (ids_r & ids_n)
