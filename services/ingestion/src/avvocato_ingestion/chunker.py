"""Chunker legal-aware.

Genera tre tipologie di chunk da ogni articolo:
- `articolo-full`: testo intero (rubrica + commi)
- `comma`: un chunk per comma
- `window`: finestre 512 tok (overlap 64) solo se articolo > 2k token

Il token count è stimato con una heuristica 1 token ≈ 4 caratteri (sufficiente
per bucketing; il conteggio esatto avviene lato LLM provider).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from avvocato_rag_core.schemas.norm import NormChunkKind


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


def build_chunks(
    *,
    partition_id: UUID,
    articolo_num: str,
    source_short_id: str,
    path: str,
    rubrica: str | None,
    commi: list[tuple[UUID, str, str]],
    effective_from_iso: str,
    effective_to_iso: str | None = None,
) -> list[BuiltChunk]:
    """Costruisce i chunk per un articolo.

    Args:
        partition_id: UUID della partizione articolo.
        articolo_num: es. "2043".
        source_short_id: es. "cc".
        path: ltree path.
        rubrica: titoletto dell'articolo (può essere None).
        commi: tuple (comma_id, numero, testo) già persistite in DB.
        effective_from_iso: ISO date del testo vigente considerato.
        effective_to_iso: ISO date fine validità; None = vigente.
    """
    out: list[BuiltChunk] = []
    base_meta = {
        "source": source_short_id,
        "articolo": articolo_num,
        "path": path,
        "partition_id": str(partition_id),
        "effective_from": effective_from_iso,
        "effective_to": effective_to_iso or "9999-12-31",
    }

    # 1. Articolo-full
    full_text = ""
    if rubrica:
        full_text += f"[Rubrica] {rubrica}\n\n"
    for _, num, text in commi:
        full_text += f"{num}. {text}\n"
    full_text = full_text.strip()
    if full_text:
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

    # 2. Per-comma
    for comma_id, num, text in commi:
        chunk_text = f"{num}. {text}" if not text.startswith(num) else text
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

    # 3. Window (solo articoli molto lunghi)
    if estimate_tokens(full_text) > 2000:
        out.extend(_window_chunks(partition_id, full_text, base_meta))

    return out


def _window_chunks(
    partition_id: UUID, text: str, base_meta: dict[str, object]
) -> list[BuiltChunk]:
    window = 2048  # caratteri ≈ 512 token
    overlap = 256  # caratteri ≈ 64 token
    chunks: list[BuiltChunk] = []
    start = 0
    while start < len(text):
        end = min(start + window, len(text))
        piece = text[start:end]
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
