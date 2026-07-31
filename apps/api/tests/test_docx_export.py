"""Test del renderer .docx: struttura, citazioni, allegato, avvertenze."""

from __future__ import annotations

import io
from datetime import date

from docx import Document

from caucus_api.services.docx_export import (
    ResolvedRef,
    extract_citation_keys,
    render_parere_docx,
)

_ANSWER = """# Inquadramento

La responsabilità è **extracontrattuale** ai sensi dell'<cite source="cc" part="articolo" num="2043"/>.

## Vie di difesa

- Contestare il *nesso causale*
- Eccepire la prescrizione breve <cite source="cc" part="articolo" num="2947"/>

1. Raccogliere il verbale
2. Scrivere alla controparte
"""


def _render(refs: list[ResolvedRef]) -> Document:
    blob = render_parere_docx(
        question="Chi risarcisce il danno da incidente?",
        answer=_ANSWER,
        refs=refs,
        generated_on=date(2026, 7, 31),
    )
    return Document(io.BytesIO(blob))


def _full_text(doc: Document) -> str:
    return "\n".join(p.text for p in doc.paragraphs)


def test_extract_citation_keys_dedup_and_order():
    keys = extract_citation_keys(_ANSWER + '<cite source="cc" part="articolo" num="2043"/>')
    assert keys == [("cc", "2043"), ("cc", "2947")]


def test_cite_tags_become_canonical_display():
    doc = _render([])
    text = _full_text(doc)
    assert "<cite" not in text
    assert "art. 2043 c.c." in text
    assert "art. 2947 c.c." in text


def test_markdown_marks_are_consumed():
    doc = _render([])
    text = _full_text(doc)
    assert "**" not in text
    assert "# " not in text
    # Il contenuto sopravvive alla conversione
    assert "Inquadramento" in text
    assert "Contestare il nesso causale" in text
    assert "Raccogliere il verbale" in text


def test_annex_lists_refs_with_vigenza_state():
    refs = [
        ResolvedRef(
            source="cc",
            num="2043",
            display="art. 2043 c.c.",
            source_title="Codice Civile",
            rubrica="Risarcimento per fatto illecito",
            text="Qualunque fatto doloso o colposo…",
            abrogato=False,
        ),
        ResolvedRef(
            source="cp",
            num="594",
            display="art. 594 c.p.",
            source_title="Codice Penale",
            abrogato=True,
        ),
        ResolvedRef(source="cc", num="9999", display="art. 9999 c.c.", found=False),
    ]
    text = _full_text(_render(refs))
    assert "Riferimenti normativi" in text
    assert "Risarcimento per fatto illecito" in text
    assert "Vigente alla data del documento" in text
    assert "ABROGATA" in text
    assert "NON trovato nel corpus" in text


def test_metadata_and_disclaimer_present():
    text = _full_text(_render([]))
    assert "Oggetto:" in text
    assert "Chi risarcisce il danno da incidente?" in text
    assert "31 luglio 2026" in text
    assert "non costituisce parere legale" in text


def test_long_ref_text_is_truncated():
    refs = [
        ResolvedRef(
            source="ccp",
            num="17",
            display="art. 17 cod. contr. pubbl.",
            text="x" * 5000,
        )
    ]
    text = _full_text(_render(refs))
    assert "[…]" in text
    assert "x" * 1600 not in text
