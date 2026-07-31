"""Test dello schema della route /norma (destinazione dei link <cite/>)."""

from __future__ import annotations

from datetime import date

from caucus_api.routes.norma import CommaOut, NormaOut


def test_norma_out_serializes_expected_contract():
    out = NormaOut(
        source="cc",
        source_title="Codice Civile",
        articolo="2043",
        rubrica="Risarcimento per fatto illecito",
        citation="art. 2043 c.c.",
        abrogato=False,
        effective_from=date(2026, 4, 17),
        effective_to=None,
        commi=[CommaOut(number="1", text="Qualunque fatto doloso o colposo…")],
        full_text=None,
        source_url="https://www.normattiva.it/",
    )
    data = out.model_dump()
    # Il frontend dipende da questi campi: cambiarli rompe la pagina /norma
    for key in ("source", "articolo", "rubrica", "citation", "abrogato", "commi"):
        assert key in data
    assert data["commi"][0]["number"] == "1"


def test_norma_out_defaults_abrogato_false():
    out = NormaOut(
        source="cp",
        source_title="Codice Penale",
        articolo="575",
        citation="art. 575 c.p.",
        effective_from=date(2026, 4, 17),
        commi=[],
    )
    assert out.abrogato is False
    assert out.rubrica is None
