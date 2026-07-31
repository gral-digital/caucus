"""Test del parsing dell'output strutturato della query expansion."""

from __future__ import annotations

from caucus_rag_core.query_expander import parse_expansion
from caucus_rag_core.query_router import ArticleRef


def test_two_line_output():
    parsed = parse_expansion(
        "QUERY: prescrizione risarcimento danno circolazione art. 2947 codice civile\n"
        "RIF: cc 2947; cc 2946; cpc 633"
    )
    assert parsed is not None
    assert parsed.text.startswith("prescrizione risarcimento")
    assert parsed.refs == (
        ArticleRef("cc", "2947"),
        ArticleRef("cc", "2946"),
        ArticleRef("cpc", "633"),
    )


def test_suffixed_and_dotted_article_numbers():
    parsed = parse_expansion("QUERY: attenuanti generiche\nRIF: cp 62-bis; cpriv 2-undecies")
    assert parsed is not None
    assert parsed.refs == (ArticleRef("cp", "62-bis"), ArticleRef("cpriv", "2-undecies"))


def test_unknown_source_and_garbage_tokens_are_dropped():
    parsed = parse_expansion("QUERY: q\nRIF: xyz 12; cc 2043; art. 5; cc")
    assert parsed is not None
    assert parsed.refs == (ArticleRef("cc", "2043"),)


def test_trailing_punctuation_is_stripped():
    """«cpp 369-bis.» (punto di coda dell'LLM) deve risolvere in 369-bis."""
    parsed = parse_expansion("QUERY: q\nRIF: cpp 369-bis.; cpc 473-bis.36")
    assert parsed is not None
    assert parsed.refs == (ArticleRef("cpp", "369-bis"), ArticleRef("cpc", "473-bis.36"))


def test_numeric_ranges_are_rejected():
    """«wb 1-21» è un intervallo, non un articolo: va scartato."""
    parsed = parse_expansion("QUERY: tutele whistleblower\nRIF: wb 1-21; wb 17; cpriv 2-undecies")
    assert parsed is not None
    assert parsed.refs == (ArticleRef("wb", "17"), ArticleRef("cpriv", "2-undecies"))


def test_no_refs_dash():
    parsed = parse_expansion("QUERY: interpretazione del contratto\nRIF: -")
    assert parsed is not None
    assert parsed.refs == ()


def test_missing_prefixes_falls_back_to_first_line():
    """Modello che ignora il formato: la prima riga è comunque la query."""
    parsed = parse_expansion("risoluzione contratto inadempimento art. 1453 codice civile")
    assert parsed is not None
    assert parsed.text.startswith("risoluzione contratto")
    assert parsed.refs == ()


def test_refs_capped_at_six_and_deduped():
    line = "RIF: " + "; ".join(["cc 1", "cc 1", "cc 2", "cc 3", "cc 4", "cc 5", "cc 6", "cc 7"])
    parsed = parse_expansion(f"QUERY: q\n{line}")
    assert parsed is not None
    assert len(parsed.refs) == 6
    assert parsed.refs[0] == ArticleRef("cc", "1")
    assert ArticleRef("cc", "7") not in parsed.refs


def test_empty_or_oversized_output_is_rejected():
    assert parse_expansion("") is None
    assert parse_expansion("QUERY: " + "x" * 700) is None
