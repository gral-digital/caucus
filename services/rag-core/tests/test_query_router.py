"""Test query router intento e disambiguazione."""

from __future__ import annotations

from caucus_rag_core.query_router import route_query


def test_traffic_intent_routes_cds():
    routed = route_query("Mi hanno fermato positivo all'etilometro con 1.1 g/l")
    assert routed.intent == "traffic"
    assert "cds" in (routed.sources or [])
    # L'art. 186 CdS è un SUGGERIMENTO del router (l'utente non l'ha citato):
    # entra come candidato, non come pin che domina il ranking.
    assert any(a.source == "cds" and a.num == "186" for a in routed.suggested_articles)


def test_homicide_volontario_suggests_art_575():
    routed = route_query("Come è definito il reato di omicidio volontario?")
    assert any(a.source == "cp" and a.num == "575" for a in routed.suggested_articles)
    assert "575" in routed.retrieval_text


def test_explicit_article_citation():
    routed = route_query("Cosa dice l'art. 2043 c.c. sul risarcimento?")
    assert any(a.source == "cc" and a.num == "2043" for a in routed.direct_articles)


def test_dolo_colpa_no_false_traffic_route():
    routed = route_query("Qual è la differenza tra dolo e colpa?")
    assert routed.intent != "traffic"
    assert "cds" not in (routed.sources or [])


def test_explicit_refs_and_heuristics_are_separated():
    """Un riferimento esplicito è vincolante; una regola di materia no.

    Regressione: la regola "contract" pinnava l'art. 1218 su qualunque domanda
    contenente "contratto", dominando il ranking anche quando l'utente citava
    un altro articolo (es. 1470 sulla vendita).
    """
    routed = route_query("Cos'è il contratto di vendita, codice civile art. 1470?")
    assert [(a.source, a.num) for a in routed.direct_articles] == [("cc", "1470")]
    assert any(a.num == "1218" for a in routed.suggested_articles)


def test_source_first_reference_order():
    """La query expansion scrive "Costituzione italiana art. 3": va riconosciuto."""
    for text, expected in [
        ("principio di uguaglianza Costituzione italiana art. 3", ("cost", "3")),
        ("contratto di vendita codice civile art. 1470", ("cc", "1470")),
        ("obblighi sicurezza d.lgs. 81/2008 art. 17", ("tusl", "17")),
        # L'LLM aggiunge aggettivi: "codice civile italiano art. 1470"
        ("contratto di vendita codice civile italiano art. 1470-1480", ("cc", "1470")),
    ]:
        refs = [(a.source, a.num) for a in route_query(text).direct_articles]
        assert expected in refs, f"{text!r} → {refs}"
