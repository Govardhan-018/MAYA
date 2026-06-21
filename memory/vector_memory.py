"""Vector memory using ChromaDB for semantic retrieval."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import chromadb
from chromadb.config import Settings

from memory.config import (
    VECTOR_COLLECTION_NAME,
    VECTOR_TOP_K,
    VECTORS_DIR,
    ensure_dirs,
)


class VectorMemory:
    """Wraps ChromaDB for embedding-based memory retrieval."""

    def __init__(self) -> None:
        self._client: Optional[chromadb.ClientAPI] = None
        self._collection: Optional[chromadb.Collection] = None

    @property
    def collection(self) -> chromadb.Collection:
        if self._collection is None:
            self._init_db()
        assert self._collection is not None
        return self._collection

    def _init_db(self) -> None:
        ensure_dirs()
        self._client = chromadb.PersistentClient(
            path=str(VECTORS_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=VECTOR_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        text: str,
        *,
        doc_type: str = "memory",
        source_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Add a text document to the vector store. Returns the document ID."""
        doc_id = uuid.uuid4().hex[:16]
        meta: dict[str, Any] = {
            "type": doc_type,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        if source_id:
            meta["source_id"] = source_id
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v

        self.collection.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[meta],
        )
        return doc_id

    def add_batch(
        self,
        texts: list[str],
        *,
        doc_type: str = "memory",
        metadatas: Optional[list[dict[str, Any]]] = None,
    ) -> list[str]:
        """Add multiple documents at once."""
        if not texts:
            return []
        ids = [uuid.uuid4().hex[:16] for _ in texts]
        now = datetime.now(tz=timezone.utc).isoformat()

        metas: list[dict[str, Any]] = []
        for i, text in enumerate(texts):
            meta: dict[str, Any] = {"type": doc_type, "created_at": now}
            if metadatas and i < len(metadatas):
                for k, v in metadatas[i].items():
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
            metas.append(meta)

        self.collection.add(ids=ids, documents=texts, metadatas=metas)
        return ids

    def search(
        self,
        query: str,
        top_k: int = VECTOR_TOP_K,
        doc_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Semantic search. Returns list of {id, text, score, metadata}."""
        where = {"type": doc_type} if doc_type else None

        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )

        out: list[dict[str, Any]] = []
        if not results or not results["ids"]:
            return out

        ids = results["ids"][0]
        docs = results["documents"][0] if results["documents"] else []
        distances = results["distances"][0] if results["distances"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []

        for i, doc_id in enumerate(ids):
            out.append({
                "id": doc_id,
                "text": docs[i] if i < len(docs) else "",
                "score": 1.0 - (distances[i] if i < len(distances) else 0.0),
                "metadata": metas[i] if i < len(metas) else {},
            })
        return out

    def delete(self, doc_id: str) -> None:
        self.collection.delete(ids=[doc_id])

    def count(self) -> int:
        return self.collection.count()

    def clear(self) -> None:
        if self._client:
            self._client.delete_collection(VECTOR_COLLECTION_NAME)
            self._collection = None
            self._init_db()
