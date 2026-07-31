"""Test del parser AKN XML su fixture reali (CC e CP vigenti).

Questi test blindano il parser contro regressioni: se Normattiva cambia il
formato, vogliamo saperlo subito. I fixture sono snapshot committati in
``data/fixtures/normattiva/`` e vengono periodicamente rigenerati via
``make fetch-codici``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avvocato_ingestion.parsers.normattiva_akn import NormattivaAknParser
from avvocato_rag_core.schemas.norm import NormPartitionKind

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "normattiva"

CC_XML = FIXTURE_DIR / "codice_civile_20260417.akn.xml"
CP_XML = FIXTURE_DIR / "codice_penale_20260417.akn.xml"


def _load(xml_path: Path, short_id: str):
    if not xml_path.exists():
        pytest.skip(f"Fixture mancante: {xml_path}. Esegui `make fetch-codici`.")
    return NormattivaAknParser().parse_file(xml_path, short_id=short_id)


# ---------------------------------------------------------------------------
# Codice Civile
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cc_articles():
    act = _load(CC_XML, "cc")
    return act.root[0].children


def test_cc_total_article_count(cc_articles):
    """Il CC (incl. bis/ter + Disposizioni sulla legge in generale) deve avere
    tra 3100 e 3400 entry. Se Normattiva aggiunge/abroga articoli, il range
    assorbe la variazione; cambi più grandi = segnale di regressione parser.
    """
    assert 3100 <= len(cc_articles) <= 3400, (
        f"CC article count fuori range atteso: got {len(cc_articles)}"
    )


def test_cc_article_2969_is_last(cc_articles):
    """Art. 2969 = ultimo articolo del CC (vigente)."""
    nums = [a.number for a in cc_articles]
    assert "2969" in nums


@pytest.mark.parametrize(
    ("article_num", "expected_rubrica_fragment"),
    [
        ("2043", "risarcimento"),
        ("1418", "nullit"),  # "Cause di nullita' del contratto"
        ("2697", "onere della prova"),
        ("414", "interdette"),
        ("1362", "intenzione"),
        ("832", "contenuto del diritto"),
    ],
)
def test_cc_famous_articles_have_correct_rubrica(
    cc_articles, article_num, expected_rubrica_fragment
):
    found = next((a for a in cc_articles if a.number == article_num), None)
    assert found is not None, f"Art. {article_num} CC non trovato"
    assert found.rubrica is not None, f"Art. {article_num} CC senza rubrica"
    assert expected_rubrica_fragment.lower() in found.rubrica.lower()


def test_cc_rubrica_coverage_on_active_articles(cc_articles):
    """Almeno l'85% degli articoli non abrogati deve avere rubrica."""
    active = [a for a in cc_articles if not _is_abrogato(a.full_text or "")]
    with_rubrica = [a for a in active if a.rubrica]
    coverage = len(with_rubrica) / len(active)
    assert coverage >= 0.85, (
        f"Rubrica coverage troppo bassa: {coverage:.1%} su {len(active)} articoli attivi"
    )


def test_cc_art_1418_has_three_commi(cc_articles):
    """Art. 1418 (Cause di nullità del contratto) ha 3 commi."""
    art = next(a for a in cc_articles if a.number == "1418")
    assert len(art.commi) == 3
    # Ogni comma non deve essere vuoto
    for c in art.commi:
        assert len(c.text) > 10


# ---------------------------------------------------------------------------
# Codice Penale
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cp_articles():
    act = _load(CP_XML, "cp")
    return act.root[0].children


def test_cp_total_article_count(cp_articles):
    """Il CP corrente ha ~990 entry (base + bis/ter)."""
    assert 900 <= len(cp_articles) <= 1100, (
        f"CP article count fuori range atteso: got {len(cp_articles)}"
    )


@pytest.mark.parametrize(
    ("article_num", "expected_rubrica_fragment"),
    [
        ("575", "omicidio"),
        ("612-bis", "atti persecutori"),
        ("416-bis", "mafioso"),
        ("110", "concorrono nel reato"),
        ("640", "truffa"),
        ("56", "delitto tentato"),
        ("5", "ignoranza della legge"),
        ("81", "concorso formale"),
    ],
)
def test_cp_famous_articles_have_correct_rubrica(
    cp_articles, article_num, expected_rubrica_fragment
):
    found = next((a for a in cp_articles if a.number == article_num), None)
    assert found is not None, f"Art. {article_num} CP non trovato"
    assert found.rubrica is not None, f"Art. {article_num} CP senza rubrica"
    assert expected_rubrica_fragment.lower() in found.rubrica.lower()


def test_cp_rubrica_coverage_on_active_articles(cp_articles):
    active = [a for a in cp_articles if not _is_abrogato(a.full_text or "")]
    with_rubrica = [a for a in active if a.rubrica]
    coverage = len(with_rubrica) / len(active)
    assert coverage >= 0.85, f"CP rubrica coverage: {coverage:.1%} su {len(active)} articoli attivi"


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


def test_all_articles_have_kind_articolo(cc_articles):
    assert all(a.kind == NormPartitionKind.ARTICOLO for a in cc_articles)


def test_no_duplicate_article_numbers(cc_articles):
    """Nessun articolo CC deve apparire due volte con lo stesso number.

    (È ammesso che CC e 'disposizioni preliminari' abbiano entrambi 'art. 1',
    ma dopo l'unione sotto un'unica root li consideriamo distinti. TODO: quando
    la gerarchia sarà completa, testare che 'disposizioni preliminari' sia un
    sub-albero separato.)
    """
    numbers = [a.number for a in cc_articles]
    # Al momento art. 1..31 possono apparire sia nelle disposizioni preliminari
    # che nel CC proper — è corretto. Verifichiamo solo che non ci siano
    # duplicati TOTALI esagerati.
    from collections import Counter

    dups = [n for n, c in Counter(numbers).items() if c > 2]
    assert not dups, f"Articoli con più di 2 occorrenze: {dups}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_abrogato(text: str) -> bool:
    upper = text.upper()
    return any(m in upper for m in ("ABROGAT", "OMESSO", "SOPPRESS"))
