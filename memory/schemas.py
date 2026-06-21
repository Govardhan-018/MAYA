"""Pydantic schemas for the Memory Layer."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── Chat ──────────────────────────────────────────────────────────────────

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chat(BaseModel):
    chat_id: str
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    messages: list[ChatMessage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    message_count: int = 0
    estimated_tokens: int = 0


# ── Chat Summary ──────────────────────────────────────────────────────────

class ChatSummary(BaseModel):
    chat_id: str
    created_at: datetime = Field(default_factory=_utcnow)
    summary: str = ""
    key_topics: list[str] = Field(default_factory=list)
    important_facts: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)
    message_count: int = 0


# ── Long-Term Memory ─────────────────────────────────────────────────────

class MemoryCategory(str, Enum):
    PROJECTS = "projects"
    PEOPLE = "people"
    PREFERENCES = "preferences"
    GOALS = "goals"
    FACTS = "facts"
    SKILLS = "skills"
    RECURRING_TASKS = "recurring_tasks"
    DECISIONS = "decisions"


class MemoryEntry(BaseModel):
    id: str
    category: MemoryCategory
    content: str
    importance: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    source_chat_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LongTermMemoryStore(BaseModel):
    version: str = "1.0.0"
    updated_at: datetime = Field(default_factory=_utcnow)
    memories: dict[str, list[MemoryEntry]] = Field(
        default_factory=lambda: {c.value: [] for c in MemoryCategory}
    )


# ── Agent History ─────────────────────────────────────────────────────────

class AgentHistoryEntry(BaseModel):
    timestamp: datetime = Field(default_factory=_utcnow)
    agent: str
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: str = "success"
    result_summary: str = ""
    duration_ms: float = 0.0
    chat_id: Optional[str] = None


# ── Planner History ──────────────────────────────────────────────────────

class PlannerHistoryEntry(BaseModel):
    timestamp: datetime = Field(default_factory=_utcnow)
    user_command: str
    plan_json: dict[str, Any] = Field(default_factory=dict)
    execution_results: list[dict[str, Any]] = Field(default_factory=list)
    response: str = ""
    duration_ms: float = 0.0
    chat_id: Optional[str] = None


# ── Brain State (recovery) ────────────────────────────────────────────────

class BrainState(BaseModel):
    active_chat_id: Optional[str] = None
    current_project: Optional[str] = None
    unfinished_tasks: list[dict[str, Any]] = Field(default_factory=list)
    queue_state: dict[str, Any] = Field(default_factory=dict)
    planner_state: dict[str, Any] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=_utcnow)
    version: str = "1.0.0"
