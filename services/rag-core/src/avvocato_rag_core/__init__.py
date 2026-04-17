"""Avvocato RAG core library.

Libreria di basso livello per retrieval, reranking e routing LLM.
Usata da apps/api (online) e services/ingestion + services/indexer (offline).
"""

from avvocato_rag_core.version import __version__

__all__ = ["__version__"]
