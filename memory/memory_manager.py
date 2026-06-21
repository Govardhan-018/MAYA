"""MemoryManager — single entry point for all memory operations.

Coordinates active chat, rotation, summarization, long-term memory,
vector storage, agent/planner history, context building, and recovery.
"""

from __future__ import annotations

import threading
import traceback
from typing import Any, Optional

from memory.active_chat import ActiveChat
from memory.agent_history import AgentHistory
from memory.chat_rotator import ChatRotator
from memory.chat_summarizer import ChatSummarizer
from memory.config import ensure_dirs
from memory.context_builder import ContextBuilder
from memory.long_term_memory import LongTermMemory
from memory.planner_history import PlannerHistory
from memory.recovery import RecoveryManager
from memory.schemas import ChatSummary, MemoryEntry
from memory.vector_memory import VectorMemory


class MemoryManager:
    """Unified interface for the MAYA memory system."""

    def __init__(self, *, lazy_vectors: bool = True) -> None:
        ensure_dirs()

        self.active_chat = ActiveChat()
        self.long_term = LongTermMemory()
        self.agent_history = AgentHistory()
        self.planner_history = PlannerHistory()
        self.summarizer = ChatSummarizer()
        self.recovery = RecoveryManager()

        self._vector: Optional[VectorMemory] = None
        self._lazy_vectors = lazy_vectors
        if not lazy_vectors:
            self._vector = VectorMemory()

        self.rotator = ChatRotator(self.active_chat, self.summarizer)
        self._context_builder: Optional[ContextBuilder] = None

        self._bg_lock = threading.Lock()

    @property
    def vector(self) -> VectorMemory:
        if self._vector is None:
            self._vector = VectorMemory()
        return self._vector

    @property
    def context_builder(self) -> ContextBuilder:
        if self._context_builder is None:
            self._context_builder = ContextBuilder(
                self.active_chat,
                self.long_term,
                self.vector,
                self.agent_history,
                self.planner_history,
            )
        return self._context_builder

    # ── startup / recovery ────────────────────────────────────────────────

    def startup(self) -> dict[str, Any]:
        """Initialize memory on Brain startup. Recovers previous state."""
        state = self.recovery.load()
        info: dict[str, Any] = {"recovered": False}

        if state.active_chat_id:
            loaded = self.active_chat.load_existing(state.active_chat_id)
            if loaded:
                info["recovered"] = True
                info["active_chat_id"] = state.active_chat_id
                info["message_count"] = self.active_chat.message_count
            else:
                self.active_chat.load_latest() or self.active_chat.create_new()
                info["active_chat_id"] = self.active_chat.chat_id
        else:
            self.active_chat.load_latest() or self.active_chat.create_new()
            info["active_chat_id"] = self.active_chat.chat_id

        self.long_term.load()
        self.agent_history.load_recent_from_disk()
        self.planner_history.load_recent_from_disk()

        self.recovery.save_active_chat(self.active_chat.chat_id or "")

        if state.unfinished_tasks:
            info["unfinished_tasks"] = state.unfinished_tasks

        if state.current_project:
            info["current_project"] = state.current_project

        return info

    # ── chat operations ───────────────────────────────────────────────────

    def add_user_message(self, content: str) -> Optional[tuple[ChatSummary, str]]:
        """Add a user message and rotate if needed. Returns rotation info or None."""
        self.active_chat.add_message("user", content)
        return self.rotator.check_and_rotate()

    def add_assistant_message(self, content: str) -> Optional[tuple[ChatSummary, str]]:
        """Add an assistant message and rotate if needed."""
        self.active_chat.add_message("assistant", content)
        return self.rotator.check_and_rotate()

    def get_context_for_planner(self, command: str) -> str:
        """Build optimized context for the planner."""
        return self.context_builder.build(command)

    def get_compact_context(self, command: str) -> str:
        """Build minimal context for the planner."""
        return self.context_builder.build_compact(command)

    # ── post-execution recording ──────────────────────────────────────────

    def record_agent_execution(
        self,
        agent: str,
        action: str,
        parameters: dict[str, Any],
        status: str = "success",
        result_summary: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        """Record an agent execution in history and vector store."""
        self.agent_history.record(
            agent=agent,
            action=action,
            parameters=parameters,
            status=status,
            result_summary=result_summary,
            duration_ms=duration_ms,
            chat_id=self.active_chat.chat_id,
        )

        if result_summary and status == "success":
            self._bg_embed(
                f"{agent}.{action}: {result_summary}",
                doc_type="agent_history",
                metadata={"agent": agent, "action": action},
            )

    def record_planner_execution(
        self,
        user_command: str,
        plan_json: dict[str, Any],
        execution_results: list[dict[str, Any]],
        response: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        self.planner_history.record(
            user_command=user_command,
            plan_json=plan_json,
            execution_results=execution_results,
            response=response,
            duration_ms=duration_ms,
            chat_id=self.active_chat.chat_id,
        )

    # ── long-term memory operations ───────────────────────────────────────

    def store_memory(
        self,
        category: str,
        content: str,
        importance: float,
        tags: Optional[list[str]] = None,
    ) -> Optional[str]:
        mid = self.long_term.add_memory(
            category=category,
            content=content,
            importance=importance,
            source_chat_id=self.active_chat.chat_id,
            tags=tags,
        )
        if mid:
            self._bg_embed(content, doc_type="long_term", metadata={"category": category, "memory_id": mid})
        return mid

    def search_memory(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        return self.long_term.search_memories(query, category=category, limit=limit)

    def search_vector(
        self,
        query: str,
        top_k: int = 5,
        doc_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return self.vector.search(query, top_k=top_k, doc_type=doc_type)

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        tags: Optional[list[str]] = None,
    ) -> bool:
        return self.long_term.update_memory(memory_id, content, importance, tags)

    def delete_memory(self, memory_id: str) -> bool:
        return self.long_term.delete_memory(memory_id)

    # ── manual chat management ────────────────────────────────────────────

    def force_rotate(self) -> tuple[Optional[ChatSummary], str]:
        """Force a chat rotation regardless of thresholds."""
        summary, new_id = self.rotator.rotate()
        self.recovery.save_active_chat(new_id)

        if summary:
            self._bg_embed(
                summary.summary,
                doc_type="chat_summary",
                metadata={"chat_id": summary.chat_id},
            )
            memories = self.summarizer.extract_memories(
                self.active_chat.get_all_messages(),
                chat_id=summary.chat_id,
            )
            if memories:
                self.long_term.add_memories_batch(memories)

        return summary, new_id

    def create_summary_of_current(self) -> Optional[ChatSummary]:
        """Summarize the current chat without rotating."""
        messages = self.active_chat.get_all_messages()
        if not messages:
            return None
        chat_id = self.active_chat.chat_id or "unknown"
        return self.summarizer.summarize_chat(chat_id, messages)

    # ── state persistence ─────────────────────────────────────────────────

    def save_state(
        self,
        *,
        project: Optional[str] = None,
        unfinished_tasks: Optional[list[dict[str, Any]]] = None,
        queue_state: Optional[dict[str, Any]] = None,
        planner_state: Optional[dict[str, Any]] = None,
    ) -> None:
        self.recovery.full_save(
            chat_id=self.active_chat.chat_id,
            project=project,
            unfinished_tasks=unfinished_tasks,
            queue_state=queue_state,
            planner_state=planner_state,
        )

    def get_status(self) -> dict[str, Any]:
        return {
            "active_chat_id": self.active_chat.chat_id,
            "message_count": self.active_chat.message_count,
            "estimated_tokens": self.active_chat.estimated_tokens,
            "long_term_summary": self.long_term.get_summary(),
            "agent_history_stats": self.agent_history.get_stats(),
            "vector_count": self._vector.count() if self._vector else 0,
            "recovery": self.recovery.get_recovery_info(),
        }

    # ── background embedding ──────────────────────────────────────────────

    def _bg_embed(
        self,
        text: str,
        doc_type: str = "memory",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Embed text in background thread. Failures are silently logged."""
        thread = threading.Thread(
            target=self._embed_safe,
            args=(text, doc_type, metadata),
            daemon=True,
        )
        thread.start()

    def _embed_safe(
        self,
        text: str,
        doc_type: str,
        metadata: Optional[dict[str, Any]],
    ) -> None:
        try:
            with self._bg_lock:
                self.vector.add(text, doc_type=doc_type, metadata=metadata or {})
        except Exception:
            pass
