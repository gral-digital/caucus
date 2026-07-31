"""Test query router intento e disambiguazione."""

from __future__ import annotations

from caucus_rag_core.query_router import route_query


def test_traffic_intent_routes_cds():
    routed = route_query("Mi hanno fermato positivo all'etilometro con 1.1 g/l")
    assert routed.intent == "traffic"
    assert "cds" in (routed.sources or [])
    assert any(a.source == "cds" and a.num == "186" for a in routed.direct_articles)


def test_homicide_volontario_pins_art_575():
    routed = route_query("Come è definito il reato di omicidio volontario?")
    assert any(a.source == "cp" and a.num == "575" for a in routed.direct_articles)
    assert "575" in routed.retrieval_text


def test_explicit_article_citation():
    routed = route_query("Cosa dice l'art. 2043 c.c. sul risarcimento?")
    assert any(a.source == "cc" and a.num == "2043" for a in routed.direct_articles)


def test_dolo_colpa_no_false_traffic_route():
    routed = route_query("Qual è la differenza tra dolo e colpa?")
    assert routed.intent != "traffic"
    assert "cds" not in (routed.sources or [])
