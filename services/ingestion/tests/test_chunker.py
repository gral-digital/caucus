"""Test del chunker: contextual retrieval e deduplicazione."""

from __future__ import annotations

from uuid import uuid4

from avvocato_ingestion.chunker import build_chunks
from avvocato_rag_core.schemas.norm import NormChunkKind


def _build(commi_texts: list[str], *, rubrica: str | None = "Risarcimento per fatto illecito"):
    commi = [(uuid4(), str(i + 1), t) for i, t in enumerate(commi_texts)]
    return build_chunks(
        partition_id=uuid4(),
        articolo_num="2043",
        source_short_id="cc",
        source_title="Codice Civile",
        path="cc.libro_0.articolo_2043",
        rubrica=rubrica,
        commi=commi,
        effective_from_iso="2026-04-17",
    )


def test_comma_chunk_has_contextual_header():
    chunks = _build(["Qualunque fatto doloso o colposo."])
    comma = next(c for c in chunks if c.chunk_kind == NormChunkKind.COMMA)
    assert "Codice Civile" in comma.text
    assert "art. 2043" in comma.text
    assert "Risarcimento per fatto illecito" in comma.text
    assert "Qualunque fatto doloso" in comma.text


def test_single_comma_article_has_no_articolo_full_duplicate():
    """Articolo con comma unico: solo il chunk comma (niente duplicato full)."""
    chunks = _build(["Qualunque fatto doloso o colposo."])
    kinds = [c.chunk_kind for c in chunks]
    assert kinds == [NormChunkKind.COMMA]


def test_multi_comma_article_has_full_and_commas():
    chunks = _build(["Primo comma.", "Secondo comma.", "Terzo comma."])
    kinds = [c.chunk_kind for c in chunks]
    assert kinds.count(NormChunkKind.ARTICOLO_FULL) == 1
    assert kinds.count(NormChunkKind.COMMA) == 3


def test_articolo_full_contains_fonte_and_rubrica_markers():
    chunks = _build(["Primo.", "Secondo."])
    full = next(c for c in chunks if c.chunk_kind == NormChunkKind.ARTICOLO_FULL)
    assert full.text.startswith("[Fonte] Codice Civile — art. 2043")
    assert "[Rubrica] Risarcimento per fatto illecito" in full.text


def test_windows_only_for_long_articles_and_carry_context():
    long_comma = "parola " * 2000  # ~14k char → > 2000 token stimati
    chunks = _build([long_comma, "Secondo comma."])
    windows = [c for c in chunks if c.chunk_kind == NormChunkKind.WINDOW]
    assert len(windows) >= 2
    # Dalla seconda finestra in poi il contesto è ripetuto
    assert windows[1].text.startswith("[Fonte] Codice Civile — art. 2043")


def test_no_commi_yields_minimal_full_chunk():
    chunks = _build([], rubrica="Solo rubrica")
    assert len(chunks) == 1
    assert chunks[0].chunk_kind == NormChunkKind.ARTICOLO_FULL
    assert "Solo rubrica" in chunks[0].text
