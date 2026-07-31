"""Test selezione passaggi rilevanti dai documenti lunghi."""

from __future__ import annotations

from caucus_api.services.document_excerpts import select_relevant_excerpts

_FILLER = "Le premesse costituiscono parte integrante del presente accordo quadro.\n" * 20


def _long_doc() -> str:
    head = "CONTRATTO DI APPALTO tra Alfa S.r.l. e Beta S.p.A.\n"
    deep_clause = (
        "Art. 47 (Penale per ritardo). In caso di ritardo nella consegna il "
        "committente applica una penale giornaliera dello 0,3 per mille.\n"
    )
    return head + _FILLER * 30 + deep_clause + _FILLER * 30


def test_short_document_is_untouched():
    text, truncated = select_relevant_excerpts("breve contratto", "penale?", budget=1000)
    assert text == "breve contratto"
    assert not truncated


def test_relevant_deep_clause_is_included():
    doc = _long_doc()
    assert len(doc) > 30_000
    text, truncated = select_relevant_excerpts(
        doc, "È valida la penale per ritardo nella consegna?", budget=10_000
    )
    assert truncated
    assert len(text) <= 10_500
    # La clausola profonda pertinente c'è, la testa pure, le omissioni sono marcate
    assert "Penale per ritardo" in text
    assert "CONTRATTO DI APPALTO" in text
    assert "omissis" in text


def test_no_relevant_window_falls_back_to_head():
    doc = _long_doc()
    text, truncated = select_relevant_excerpts(doc, "xyzabc quantistica", budget=5_000)
    assert truncated
    assert text.startswith("CONTRATTO DI APPALTO")
    assert len(text) <= 5_000
