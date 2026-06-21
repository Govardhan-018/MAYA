"""Context builder — assembles an optimized context package for the planner.

Pulls from: active chat, long-term memory, vector memory, agent history.
Minimizes token usage while maximizing relevance.
"""

from __future__ import annotations

from typing import Any, Optional

from memory.active_chat import ActiveChat
from memory.agent_history import AgentHistory
from memory.config import CONTEXT_MAX_TOKENS, RECENT_MESSAGES_LIMIT
from memory.long_term_memory import LongTermMemory
from memory.planner_history import PlannerHistory
from memory.vector_memory import VectorMemory


def _estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[...truncated]"


class ContextBuilder:
    """Builds an optimized context string for the planner/response generator."""

    def __init__(
        self,
        active_chat: ActiveChat,
        long_term: LongTermMemory,
        vector: VectorMemory,
        agent_history: AgentHistory,
        planner_history: PlannerHistory,
    ) -> None:
        self._active_chat = active_chat
        self._long_term = long_term
        self._vector = vector
        self._agent_history = agent_history
        self._planner_history = planner_history

    def build(
        self,
        command: str,
        *,
        max_tokens: int = CONTEXT_MAX_TOKENS,
        include_vectors: bool = True,
    ) -> str:
        """Build a context string for *command*, staying under *max_tokens*."""
        sections: list[tuple[str, str, int]] = []
        budget = max_tokens

        # 1. Recent conversation (highest priority)
        recent_text = self._active_chat.get_messages_as_text(
            limit=RECENT_MESSAGES_LIMIT
        )
        if recent_text:
            tokens = _estimate_tokens(recent_text)
            allocation = min(tokens, budget // 3)
            recent_text = _truncate_to_tokens(recent_text, allocation)
            sections.append(("RECENT CONVERSATION", recent_text, _estimate_tokens(recent_text)))
            budget -= _estimate_tokens(recent_text)

        # 2. Relevant long-term memories
        lt_results = self._long_term.search_memories(command, limit=5)
        if lt_results:
            lt_lines = [f"- {m.content}" for m in lt_results]
            lt_text = "\n".join(lt_lines)
            tokens = _estimate_tokens(lt_text)
            allocation = min(tokens, budget // 3)
            lt_text = _truncate_to_tokens(lt_text, allocation)
            sections.append(("RELEVANT MEMORIES", lt_text, _estimate_tokens(lt_text)))
            budget -= _estimate_tokens(lt_text)

        # 3. Vector search for semantic matches
        if include_vectors and budget > 200:
            try:
                vec_results = self._vector.search(command, top_k=3)
                if vec_results:
                    vec_lines = [f"- {r['text'][:200]}" for r in vec_results if r.get("text")]
                    if vec_lines:
                        vec_text = "\n".join(vec_lines)
                        vec_text = _truncate_to_tokens(vec_text, budget // 3)
                        sections.append(("RELATED CONTEXT", vec_text, _estimate_tokens(vec_text)))
                        budget -= _estimate_tokens(vec_text)
            except Exception:
                pass

        # 4. Recent agent history
        if budget > 100:
            history_text = self._agent_history.get_recent_as_text(limit=5)
            if history_text:
                history_text = _truncate_to_tokens(history_text, min(budget // 2, 500))
                sections.append(("RECENT ACTIONS", history_text, _estimate_tokens(history_text)))

        # Assemble
        parts: list[str] = []
        for header, content, _ in sections:
            parts.append(f"--- {header} ---")
            parts.append(content)
        return "\n\n".join(parts)

    def build_compact(self, command: str) -> str:
        """Minimal context — recent chat + top memories only."""
        parts: list[str] = []

        recent = self._active_chat.get_messages_as_text(limit=5)
        if recent:
            parts.append(recent)

        memories = self._long_term.search_memories(command, limit=3)
        if memories:
            mem_text = " | ".join(m.content for m in memories)
            parts.append(f"Memories: {mem_text}")

        return "\n".join(parts)
