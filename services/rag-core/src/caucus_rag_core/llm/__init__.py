"""LLM router via LiteLLM.

Punto singolo di contatto con i provider (Vertex AI, Anthropic via Vertex, …).
Il resto del codice vede solo `LLMRouter.chat(...)` e `LLMRouter.chat_stream(...)`.
"""

from caucus_rag_core.llm.router import LLMChunk, LLMMessage, LLMRouter

__all__ = ["LLMChunk", "LLMMessage", "LLMRouter"]
