"""Export .docx del parere: markdown + tag ``<cite/>`` → documento Word.

Il valore non è la conversione in sé ma il trust layer dentro il documento:
ogni citazione è ri-verificata server-side contro il corpus al momento
dell'export, resa nella forma citazionale canonica italiana, e riportata in
un allegato «Riferimenti normativi» con rubrica, stato di vigenza (con
avvertenza esplicita se abrogata o non trovata) e testo della norma.

Formattazione da studio: Times New Roman 12, corpo giustificato con
interlinea 1.3, margini 2,5 cm, numeri di pagina, nota di trasparenza AI in
coda. Il markdown supportato è il sottoinsieme che il modello produce
davvero: titoli #/##/###, liste puntate e numerate, **grassetto**, *corsivo*.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.text.paragraph import Paragraph

from caucus_rag_core.schemas.citation import NormCitation

_CITE_RE = re.compile(
    r'<cite\s+source="([a-z0-9-]+)"\s+part="[a-z]+"\s+num="([^"]+)"(?:\s+comma="([^"]+)")?\s*/>',
    re.IGNORECASE,
)

_INK = RGBColor(0x1A, 0x1A, 0x1A)
_MUTED = RGBColor(0x6B, 0x72, 0x80)
_WARN = RGBColor(0x9A, 0x3B, 0x12)

_MONTHS_IT = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)


@dataclass(frozen=True, slots=True)
class ResolvedRef:
    """Una citazione dell'answer risolta contro il corpus."""

    source: str
    num: str
    display: str
    source_title: str | None = None
    rubrica: str | None = None
    text: str | None = None
    abrogato: bool = False
    found: bool = True


def extract_citation_keys(answer: str) -> list[tuple[str, str]]:
    """Coppie (source, num) citate nell'answer, dedup, in ordine di apparizione."""
    keys: list[tuple[str, str]] = []
    for m in _CITE_RE.finditer(answer):
        key = (m.group(1).lower(), m.group(2).lower())
        if key not in keys:
            keys.append(key)
    return keys


def cite_display(source: str, num: str, comma: str | None = None) -> str:
    citation = NormCitation(source=source, part="articolo", num=num, comma=comma)
    display: str = citation.to_display()
    return display


def _format_date_it(d: date) -> str:
    return f"{d.day} {_MONTHS_IT[d.month - 1]} {d.year}"


# ---------------------------------------------------------------- inline runs

_INLINE_RE = re.compile(r"(\*\*.+?\*\*|\*[^*\n]+?\*|<cite\s+[^>]*/>)")


def _add_inline(par: Paragraph, text: str, *, bold: bool = False, italic: bool = False) -> None:
    """Rende un segmento con **grassetto**, *corsivo* e tag <cite/> in run Word."""
    for piece in _INLINE_RE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            _add_inline(par, piece[2:-2], bold=True, italic=italic)
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            _add_inline(par, piece[1:-1], bold=bold, italic=True)
        else:
            m = _CITE_RE.fullmatch(piece)
            if m:
                display = cite_display(m.group(1).lower(), m.group(2).lower(), m.group(3))
                run = par.add_run(display)
                run.bold = True
            else:
                run = par.add_run(piece)
                run.bold = bold
                run.italic = italic


# ---------------------------------------------------------------- markdown

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")


def _render_markdown(doc: DocumentObject, text: str) -> None:
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if m := _HEADING_RE.match(line):
            level = min(len(m.group(1)), 3)
            par = doc.add_paragraph(style=f"Caucus Heading {level}")
            _add_inline(par, m.group(2).strip().strip("*").strip())
            continue
        if m := _BULLET_RE.match(line):
            par = doc.add_paragraph(style="Caucus Bullet")
            _add_inline(par, m.group(1))
            continue
        if m := _ORDERED_RE.match(line):
            par = doc.add_paragraph(style="Caucus Numbered")
            _add_inline(par, m.group(1))
            continue
        if line.startswith(">"):
            par = doc.add_paragraph(style="Caucus Quote")
            _add_inline(par, line.lstrip("> "))
            continue
        par = doc.add_paragraph(style="Caucus Body")
        _add_inline(par, line)


# ---------------------------------------------------------------- styles

def _base_style(doc: DocumentObject, name: str, *, size: float, bold: bool = False) -> Any:
    style = doc.styles.add_style(name, 1)  # WD_STYLE_TYPE.PARAGRAPH
    style.font.name = "Times New Roman"
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = _INK
    # Word usa il font east-asia per i caratteri non latini: senza questo
    # fallback alcune build applicano il default del tema al posto del serif.
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), "Times New Roman")
    return style


def _setup_styles(doc: DocumentObject) -> None:
    body = _base_style(doc, "Caucus Body", size=12)
    body.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    body.paragraph_format.line_spacing = 1.3
    body.paragraph_format.space_after = Pt(6)

    for level, size in ((1, 14), (2, 12.5), (3, 12)):
        h = _base_style(doc, f"Caucus Heading {level}", size=size, bold=True)
        h.paragraph_format.space_before = Pt(14 if level == 1 else 10)
        h.paragraph_format.space_after = Pt(6)
        h.paragraph_format.keep_with_next = True

    for name in ("Caucus Bullet", "Caucus Numbered"):
        lst = _base_style(doc, name, size=12)
        lst.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        lst.paragraph_format.line_spacing = 1.3
        lst.paragraph_format.space_after = Pt(3)
        lst.paragraph_format.left_indent = Cm(0.75)
        # Elenco tipografico semplice (trattino): niente numerazione OOXML,
        # che python-docx non sa definire senza template — il testo resta
        # editabile e lo stile uniforme.
        lst.paragraph_format.first_line_indent = Cm(-0.35)

    quote = _base_style(doc, "Caucus Quote", size=11.5)
    quote.font.italic = True
    quote.paragraph_format.left_indent = Cm(1.0)
    quote.paragraph_format.line_spacing = 1.25
    quote.paragraph_format.space_after = Pt(6)

    small = _base_style(doc, "Caucus Small", size=9)
    small.font.color.rgb = _MUTED
    small.paragraph_format.line_spacing = 1.15


def _add_page_numbers(doc: DocumentObject) -> None:
    footer_par = doc.sections[0].footer.paragraphs[0]
    footer_par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer_par.add_run()
    run.font.name = "Times New Roman"
    run.font.size = Pt(9)
    run.font.color.rgb = _MUTED
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)


def _hr(doc: DocumentObject) -> None:
    par = doc.add_paragraph(style="Caucus Body")
    ppr = par._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:color"), "999999")
    borders.append(bottom)
    ppr.append(borders)


# ---------------------------------------------------------------- documento

def render_parere_docx(
    *,
    question: str,
    answer: str,
    refs: list[ResolvedRef],
    generated_on: date,
) -> bytes:
    doc = Document()
    _setup_styles(doc)

    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    title = doc.add_paragraph(style="Caucus Heading 1")
    run = title.add_run("PARERE")
    run.font.size = Pt(18)
    sub = doc.add_paragraph(style="Caucus Small")
    sub.add_run("Bozza di lavoro assistita da AI — da rivedere prima dell'uso professionale")

    meta = doc.add_paragraph(style="Caucus Body")
    meta.add_run("Oggetto: ").bold = True
    _add_inline(meta, question.strip())
    dt = doc.add_paragraph(style="Caucus Body")
    dt.add_run("Data: ").bold = True
    dt.add_run(_format_date_it(generated_on))
    _hr(doc)

    _render_markdown(doc, answer)

    if refs:
        _hr(doc)
        annex = doc.add_paragraph(style="Caucus Heading 1")
        annex.add_run("Riferimenti normativi")
        note = doc.add_paragraph(style="Caucus Small")
        note.add_run(
            "Ogni riferimento è stato verificato automaticamente sul corpus normativo "
            "indicizzato (testi consolidati Normattiva / EUR-Lex) alla data del documento."
        )
        for ref in refs:
            head = doc.add_paragraph(style="Caucus Heading 3")
            label = ref.display
            if ref.source_title:
                label += f" — {ref.source_title}"
            head.add_run(label)
            if ref.rubrica:
                rub = doc.add_paragraph(style="Caucus Body")
                rub.add_run(f"Rubrica: {ref.rubrica}").italic = True
            status = doc.add_paragraph(style="Caucus Body")
            if not ref.found:
                warn = status.add_run(
                    "⚠ Riferimento NON trovato nel corpus indicizzato: verificare "
                    "manualmente su fonte ufficiale prima dell'uso."
                )
                warn.bold = True
                warn.font.color.rgb = _WARN
            elif ref.abrogato:
                warn = status.add_run(
                    "⚠ Disposizione ABROGATA: citarla come vigente è un errore. "
                    "Verificare la disciplina successiva."
                )
                warn.bold = True
                warn.font.color.rgb = _WARN
            else:
                ok = status.add_run("Vigente alla data del documento.")
                ok.font.color.rgb = _MUTED
            if ref.text:
                excerpt = ref.text.strip()
                if len(excerpt) > 1500:
                    excerpt = excerpt[:1500].rstrip() + " […]"
                quote = doc.add_paragraph(style="Caucus Quote")
                quote.add_run(excerpt)

    _hr(doc)
    disclaimer = doc.add_paragraph(style="Caucus Small")
    disclaimer.add_run(
        "Documento generato con Caucus, assistente AI open source per il diritto "
        "italiano. Le citazioni sono verificate automaticamente contro il corpus "
        "indicizzato; il documento non costituisce parere legale né instaura un "
        "rapporto professionale. Generato il " + _format_date_it(generated_on) + "."
    )
    _add_page_numbers(doc)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
