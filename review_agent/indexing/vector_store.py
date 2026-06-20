"""ChromaDB vector store wrapper for code chunk retrieval."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_COLLECTION = "review_sentinel_code"


class VectorStore:
    """Thin wrapper around ChromaDB for storing and querying code chunks."""

    def __init__(self, persist_path: str | None = None) -> None:
        self._path = persist_path or os.environ.get("CHROMA_DB_PATH", "./data/chroma_db")
        self._client = None
        self._collection = None

    def _get_client(self):
        if self._client is None:
            import chromadb

            self._client = chromadb.PersistentClient(path=str(self._path))
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=_DEFAULT_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        """Store code chunks with their embeddings.

        Args:
            chunks: List of dicts with keys: id, content, file_path, symbol_name, language.
            embeddings: Corresponding embedding vectors.
        """
        col = self._get_collection()
        ids = [c["id"] for c in chunks]
        docs = [c["content"] for c in chunks]
        metas = [
            {
                "file_path": c.get("file_path", ""),
                "symbol_name": c.get("symbol_name", ""),
                "language": c.get("language", ""),
                "start_line": c.get("start_line", 0),
                "end_line": c.get("end_line", 0),
            }
            for c in chunks
        ]
        col.upsert(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)
        logger.debug("Upserted %d chunks into ChromaDB.", len(chunks))

    def query(
        self,
        query_embedding: list[float],
        k: int = 5,
        filter_language: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve top-k similar chunks.

        Args:
            query_embedding: Embedding vector to search with.
            k: Number of results.
            filter_language: Optional language filter.

        Returns:
            List of result dicts with content and metadata.
        """
        col = self._get_collection()
        where: dict | None = {"language": filter_language} if filter_language else None

        try:
            results = col.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("ChromaDB query failed: %s", exc)
            return []

        output: list[dict[str, Any]] = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, dists):
            output.append({"content": doc, "metadata": meta, "distance": dist})

        return output

    def count(self) -> int:
        """Return total number of stored chunks."""
        try:
            return self._get_collection().count()
        except Exception:
            return 0
