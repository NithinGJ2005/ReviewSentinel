"""Embedder — generates embeddings for code chunks and provides retrieval."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from review_agent.indexing.chunker import chunk_file, CodeChunk
from review_agent.indexing.vector_store import VectorStore

logger = logging.getLogger(__name__)

_SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".tox", "dist", "build", ".mypy_cache", ".pytest_cache",
}
_SOURCE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rb", ".rs", ".cpp", ".c", ".cs", ".php", ".swift",
}


def _chunk_id(chunk: CodeChunk) -> str:
    key = f"{chunk.file_path}:{chunk.symbol_name}:{chunk.start_line}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


class EmbeddingModel:
    """Lazy-loaded sentence-transformers model."""

    _instance = None

    @classmethod
    def get(cls) -> "EmbeddingModel":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            model_name = os.environ.get(
                "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
            )
            logger.info("Loading embedding model: %s", model_name)
            self._model = SentenceTransformer(model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        embeddings = model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()


class RepositoryIndexer:
    """Indexes a repository into ChromaDB for RAG context retrieval."""

    def __init__(
        self,
        repo_path: str = ".",
        chroma_path: str | None = None,
        batch_size: int = 32,
    ) -> None:
        self._repo_path = Path(repo_path).resolve()
        self._store = VectorStore(persist_path=chroma_path)
        self._model = EmbeddingModel.get()
        self._batch_size = batch_size

    def _iter_source_files(self):
        for path in self._repo_path.rglob("*"):
            if path.is_file() and path.suffix.lower() in _SOURCE_EXTS:
                # Skip hidden dirs and known non-source dirs
                parts = set(path.parts)
                if parts.intersection(_SKIP_DIRS):
                    continue
                yield str(path)

    def index_all(self) -> dict[str, int]:
        """Walk and index all source files."""
        files_count = 0
        chunks_count = 0
        batch_chunks: list[CodeChunk] = []

        for fpath in self._iter_source_files():
            chunks = chunk_file(fpath)
            batch_chunks.extend(chunks)
            files_count += 1

            if len(batch_chunks) >= self._batch_size:
                self._flush_batch(batch_chunks)
                chunks_count += len(batch_chunks)
                batch_chunks = []

        if batch_chunks:
            self._flush_batch(batch_chunks)
            chunks_count += len(batch_chunks)

        logger.info("Indexed %d files, %d chunks.", files_count, chunks_count)
        return {"files": files_count, "chunks": chunks_count}

    def _flush_batch(self, chunks: list[CodeChunk]) -> None:
        texts = [c.content[:2000] for c in chunks]  # cap to avoid huge embeddings
        embeddings = self._model.embed(texts)
        records = [
            {
                "id": _chunk_id(c),
                "content": c.content[:4000],
                "file_path": c.file_path,
                "symbol_name": c.symbol_name,
                "language": c.language,
                "start_line": c.start_line,
                "end_line": c.end_line,
            }
            for c in chunks
        ]
        self._store.upsert_chunks(records, embeddings)

    def retrieve_context_for_file(
        self, file_path: str, k: int = 5
    ) -> list[dict[str, Any]]:
        """Query the vector store for chunks related to a given file."""
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")[:2000]
        except Exception:
            return []

        embedding = self._model.embed([content])[0]
        language = Path(file_path).suffix.lstrip(".")
        return self._store.query(embedding, k=k, filter_language=language or None)
