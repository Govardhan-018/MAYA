"""Long-term memory storage — persistent facts across all conversations."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from memory.config import (
    IMPORTANCE_THRESHOLD,
    LONG_TERM_MEMORY_PATH,
    ensure_dirs,
)
from memory.schemas import (
    LongTermMemoryStore,
    MemoryCategory,
    MemoryEntry,
)


class LongTermMemory:
    """Manages the long-term memory JSON store."""

    def __init__(self) -> None:
        self._store: Optional[LongTermMemoryStore] = None

    @property
    def store(self) -> LongTermMemoryStore:
        if self._store is None:
            self.load()
        assert self._store is not None
        return self._store

    def load(self) -> None:
        ensure_dirs()
        if LONG_TERM_MEMORY_PATH.exists():
            data = json.loads(
                LONG_TERM_MEMORY_PATH.read_text(encoding="utf-8")
            )
            self._store = LongTermMemoryStore.model_validate(data)
        else:
            self._store = LongTermMemoryStore()
            self._save()

    def _save(self) -> None:
        ensure_dirs()
        self.store.updated_at = datetime.now(tz=timezone.utc)
        LONG_TERM_MEMORY_PATH.write_text(
            json.dumps(
                self.store.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

    def add_memory(
        self,
        category: str,
        content: str,
        importance: float,
        *,
        source_chat_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """Add a memory if it meets the importance threshold. Returns the ID or None."""
        if importance < IMPORTANCE_THRESHOLD:
            return None

        cat = MemoryCategory(category)
        if self._is_duplicate(cat, content):
            return None

        entry = MemoryEntry(
            id=uuid.uuid4().hex[:12],
            category=cat,
            content=content,
            importance=importance,
            source_chat_id=source_chat_id,
            tags=tags or [],
            metadata=metadata or {},
        )
        self.store.memories[cat.value].append(entry)
        self._save()
        return entry.id

    def add_memories_batch(self, memories: list[dict[str, Any]]) -> list[str]:
        """Add multiple memories at once. Returns list of stored IDs."""
        stored: list[str] = []
        for mem in memories:
            mid = self.add_memory(
                category=mem.get("category", "facts"),
                content=mem.get("content", ""),
                importance=mem.get("importance", 0.0),
                source_chat_id=mem.get("source_chat_id"),
                tags=mem.get("tags", []),
                metadata=mem.get("metadata", {}),
            )
            if mid:
                stored.append(mid)
        return stored

    def get_memories(self, category: Optional[str] = None) -> list[MemoryEntry]:
        if category:
            return list(self.store.memories.get(category, []))
        all_memories: list[MemoryEntry] = []
        for entries in self.store.memories.values():
            all_memories.extend(entries)
        return all_memories

    def search_memories(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Simple keyword search across memories."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        candidates = self.get_memories(category)

        scored: list[tuple[float, MemoryEntry]] = []
        for mem in candidates:
            content_lower = mem.content.lower()
            tag_text = " ".join(mem.tags).lower()

            if query_lower in content_lower:
                score = 1.0
            else:
                matches = sum(1 for w in query_words if w in content_lower or w in tag_text)
                score = matches / max(len(query_words), 1)

            if score > 0:
                scored.append((score * mem.importance, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in scored[:limit]]

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        tags: Optional[list[str]] = None,
    ) -> bool:
        for entries in self.store.memories.values():
            for entry in entries:
                if entry.id == memory_id:
                    if content is not None:
                        entry.content = content
                    if importance is not None:
                        entry.importance = importance
                    if tags is not None:
                        entry.tags = tags
                    entry.updated_at = datetime.now(tz=timezone.utc)
                    self._save()
                    return True
        return False

    def delete_memory(self, memory_id: str) -> bool:
        for cat, entries in self.store.memories.items():
            for i, entry in enumerate(entries):
                if entry.id == memory_id:
                    entries.pop(i)
                    self._save()
                    return True
        return False

    def get_memory_by_id(self, memory_id: str) -> Optional[MemoryEntry]:
        for entries in self.store.memories.values():
            for entry in entries:
                if entry.id == memory_id:
                    return entry
        return None

    def get_summary(self) -> dict[str, int]:
        return {
            cat: len(entries)
            for cat, entries in self.store.memories.items()
        }

    def get_all_as_text(self, max_per_category: int = 5) -> str:
        """Compact text representation for context building."""
        parts: list[str] = []
        for cat, entries in self.store.memories.items():
            if not entries:
                continue
            top = sorted(entries, key=lambda e: e.importance, reverse=True)[:max_per_category]
            parts.append(f"[{cat.upper()}]")
            for e in top:
                parts.append(f"- {e.content}")
        return "\n".join(parts)

    def _is_duplicate(self, category: MemoryCategory, content: str) -> bool:
        content_lower = content.lower().strip()
        for entry in self.store.memories.get(category.value, []):
            if entry.content.lower().strip() == content_lower:
                return True
        return False
