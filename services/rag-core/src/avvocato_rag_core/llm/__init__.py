"""LLM router via LiteLLM.

Punto singolo di contatto con i provider (Vertex AI, Anthropic via Vertex, …).
Il resto del codice vede solo `LLMRouter.chat(...)` e `LLMRouter.chat_stream(...)`.
"""

from avvocato_rag_core.llm.router import LLMRouter, LLMMessage, LLMChunk

__all__ = ["LLMRouter", "LLMMessage", "LLMChunk"]
