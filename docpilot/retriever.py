"""Qdrant retriever exposed as a LangChain BaseRetriever, so AgentLens traces it."""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_ollama import OllamaEmbeddings
from qdrant_client import QdrantClient

_clients: dict[str, QdrantClient] = {}


def get_client(path: str) -> QdrantClient:
    # Local-mode Qdrant allows one client per storage folder per process.
    if path not in _clients:
        _clients[path] = QdrantClient(path=path)
    return _clients[path]


class DocsRetriever(BaseRetriever):
    qdrant_path: str
    collection: str
    embed_model: str
    ollama_url: str
    k: int = 4
    max_chunk_chars: int = 1200

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun,
                                **kwargs: Any) -> list[Document]:
        emb = OllamaEmbeddings(model=self.embed_model, base_url=self.ollama_url)
        vec = emb.embed_query(f"search_query: {query}")
        hits = get_client(self.qdrant_path).query_points(self.collection, query=vec, limit=self.k).points
        return [Document(page_content=h.payload["text"][: self.max_chunk_chars],
                         metadata={k: v for k, v in h.payload.items() if k != "text"} | {"score": h.score})
                for h in hits]


def _close_all() -> None:
    for c in _clients.values():
        c.close()
    _clients.clear()


import atexit  # noqa: E402

atexit.register(_close_all)
