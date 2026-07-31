"""Selezione dei passaggi rilevanti da un documento lungo.

Quando il documento supera il budget di contesto, il taglio "solo testa"
perde le clausole in fondo — che nei contratti sono spesso quelle che
contano (penali, foro, recesso). Qui si selezionano, oltre alla testa del
documento (identità: parti, oggetto), le finestre più pertinenti alla
domanda con uno scoring lessicale in-memory: deterministico, zero latenza,
nessuna dipendenza. Le omissioni sono marcate esplicitamente — il modello
deve sapere cosa NON sta vedendo.
"""

from __future__ import annotations

import re

# La testa del documento è sempre inclusa: identità delle parti e oggetto.
_HEAD_CHARS = 3_000
_WINDOW_CHARS = 1_200
_OMISSION_MARK = "[… omissis: passaggi non pertinenti alla domanda …]"

_TOKEN_RE = re.compile(r"[a-zà-ù0-9]{4,}")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _windows(text: str) -> list[tuple[int, str]]:
    """Spezza in finestre ~_WINDOW_CHARS rispettando i confini di paragrafo."""
    out: list[tuple[int, str]] = []
    pos = 0
    current: list[str] = []
    current_start = 0
    for para in text.split("\n"):
        if not current:
            current_start = pos
        current.append(para)
        pos += len(para) + 1
        if sum(len(p) + 1 for p in current) >= _WINDOW_CHARS:
            out.append((current_start, "\n".join(current)))
            current = []
    if current:
        out.append((current_start, "\n".join(current)))
    return out


def select_relevant_excerpts(text: str, question: str, *, budget: int) -> tuple[str, bool]:
    """(estratto, truncated): il documento intero se sta nel budget, altrimenti
    testa + finestre più pertinenti alla domanda, in ordine di documento, con
    marcatori di omissione tra parti non contigue."""
    if len(text) <= budget:
        return text, False

    q_tokens = _tokens(question)
    head = text[:_HEAD_CHARS]
    remaining_budget = budget - len(head) - 200  # margine per i marcatori

    scored: list[tuple[float, int, str]] = []
    for start, window in _windows(text[_HEAD_CHARS:]):
        w_tokens = _tokens(window)
        if not w_tokens:
            continue
        overlap = len(q_tokens & w_tokens)
        if overlap == 0:
            continue
        scored.append((overlap / max(len(q_tokens), 1), start + _HEAD_CHARS, window))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked: list[tuple[int, str]] = []
    used = 0
    for _, start, window in scored:
        if used + len(window) > remaining_budget:
            continue
        picked.append((start, window))
        used += len(window)
        if used >= remaining_budget * 0.95:
            break

    # Nessuna finestra pertinente: meglio la testa lunga che niente.
    if not picked:
        return text[:budget].rstrip(), True

    picked.sort(key=lambda x: x[0])
    parts = [head.rstrip()]
    last_end = _HEAD_CHARS
    for start, window in picked:
        if start > last_end:
            parts.append(_OMISSION_MARK)
        parts.append(window.strip())
        last_end = start + len(window)
    if last_end < len(text):
        parts.append(_OMISSION_MARK)
    return "\n\n".join(parts), True
