"""Chunker legal-aware con contextual retrieval.

Genera chunk da ogni articolo:
- `articolo-full`: testo intero (header contestuale + rubrica + commi),
  SOLO se l'articolo ha più di un comma (con un comma unico sarebbe un
  duplicato quasi identico del chunk comma: doppio costo embedding e due
  hit ridondanti nei top-k; misurato ~1450 coppie nel solo CC).
- `comma`: un chunk per comma, con **prefisso contestuale** (fonte, articolo,
  rubrica): un comma nudo tipo "1. Il presente decreto disciplina…" è
  indistinguibile da migliaia di altri commi di rinvio: il contesto deve
  stare NEL testo embeddato, non solo nel payload (contextual retrieval).
- `window`: finestre 512 tok (overlap 64) solo se articolo > 2k token.

Il token count è stimato con una heuristica 1 token ≈ 4 caratteri (sufficiente
per bucketing; il conteggio esatto avviene lato LLM provider).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from caucus_rag_core.schemas.norm import NormChunkKind


@dataclass(frozen=True, slots=True)
class BuiltChunk:
    id: UUID
    partition_id: UUID
    comma_id: UUID | None
    chunk_kind: NormChunkKind
    text: str
    token_count: int
    metadata: dict[str, object]


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _context_header(source_title: str, articolo_num: str, rubrica: str | None) -> str:
    """Header contestuale compatto: "Codice Civile — art. 2043 (Risarcimento…)"."""
    header = f"{source_title} — art. {articolo_num}"
    if rubrica:
        header += f" ({rubrica})"
    return header


def build_chunks(
    *,
    partition_id: UUID,
    articolo_num: str,
    source_short_id: str,
    source_title: str,
    path: str,
    rubrica: str | None,
    commi: list[tuple[UUID, str, str]],
    effective_from_iso: str,
    effective_to_iso: str | None = None,
    abrogato: bool = False,
) -> list[BuiltChunk]:
    """Costruisce i chunk per un articolo.

    Args:
        partition_id: UUID della partizione articolo.
        articolo_num: es. "2043".
        source_short_id: es. "cc".
        source_title: titolo leggibile della fonte, es. "Codice Civile".
        path: ltree path.
        rubrica: titoletto dell'articolo (può essere None).
        commi: tuple (comma_id, numero, testo) già persistite in DB.
        effective_from_iso: ISO date del testo vigente considerato.
        effective_to_iso: ISO date fine validità; None = vigente.
        abrogato: True se l'articolo risulta abrogato/soppresso.
    """
    out: list[BuiltChunk] = []
    base_meta = {
        "source": source_short_id,
        "articolo": articolo_num,
        "path": path,
        "partition_id": str(partition_id),
        "effective_from": effective_from_iso,
        "effective_to": effective_to_iso or "9999-12-31",
        "abrogato": abrogato,
    }
    header = _context_header(source_title, articolo_num, rubrica)

    # 1. Articolo-full: solo con 2+ commi (vedi docstring del modulo).
    full_text = f"[Fonte] {header}\n"
    if rubrica:
        full_text += f"[Rubrica] {rubrica}\n"
    full_text += "\n"
    for _, num, text in commi:
        full_text += f"{num}. {text}\n"
    full_text = full_text.strip()
    if commi and len(commi) > 1:
        out.append(
            BuiltChunk(
                id=uuid4(),
                partition_id=partition_id,
                comma_id=None,
                chunk_kind=NormChunkKind.ARTICOLO_FULL,
                text=full_text,
                token_count=estimate_tokens(full_text),
                metadata={**base_meta, "kind": "articolo-full"},
            )
        )

    # 2. Per-comma con prefisso contestuale.
    for comma_id, num, text in commi:
        body = f"{num}. {text}" if not text.startswith(f"{num}.") else text
        chunk_text = f"[Fonte] {header}, comma {num}\n\n{body}"
        out.append(
            BuiltChunk(
                id=uuid4(),
                partition_id=partition_id,
                comma_id=comma_id,
                chunk_kind=NormChunkKind.COMMA,
                text=chunk_text,
                token_count=estimate_tokens(chunk_text),
                metadata={**base_meta, "kind": "comma", "comma": num, "comma_id": str(comma_id)},
            )
        )

    # 3. Articolo senza commi (es. solo rubrica): un chunk articolo-full minimo.
    if not commi and full_text:
        out.append(
            BuiltChunk(
                id=uuid4(),
                partition_id=partition_id,
                comma_id=None,
                chunk_kind=NormChunkKind.ARTICOLO_FULL,
                text=full_text,
                token_count=estimate_tokens(full_text),
                metadata={**base_meta, "kind": "articolo-full"},
            )
        )

    # 4. Window (solo articoli molto lunghi).
    if estimate_tokens(full_text) > 2000:
        out.extend(_window_chunks(partition_id, full_text, base_meta, header))

    return out


def _window_chunks(
    partition_id: UUID,
    text: str,
    base_meta: dict[str, object],
    header: str,
) -> list[BuiltChunk]:
    window = 2048  # caratteri ≈ 512 token
    overlap = 256  # caratteri ≈ 64 token
    chunks: list[BuiltChunk] = []
    start = 0
    while start < len(text):
        end = min(start + window, len(text))
        piece = text[start:end]
        # Anche le window portano il contesto: una finestra a metà di un
        # articolo lungo non contiene né fonte né numero.
        if start > 0:
            piece = f"[Fonte] {header} (segue)\n\n{piece}"
        chunks.append(
            BuiltChunk(
                id=uuid4(),
                partition_id=partition_id,
                comma_id=None,
                chunk_kind=NormChunkKind.WINDOW,
                text=piece,
                token_count=estimate_tokens(piece),
                metadata={**base_meta, "kind": "window", "window_start": start},
            )
        )
        if end == len(text):
            break
        start = end - overlap
    return chunks
