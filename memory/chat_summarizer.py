"""Summarizes chat conversations using Ollama for archival and memory extraction."""

from __future__ import annotations

import json
import re
import textwrap
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import ollama

from memory.config import (
    CHAT_SUMMARIES_DIR,
    MEMORY_OLLAMA_BASE_URL,
    SUMMARIZER_MODEL,
    SUMMARIZER_NUM_CTX,
    SUMMARIZER_TEMPERATURE,
    ensure_dirs,
)
from memory.schemas import ChatMessage, ChatSummary


_SUMMARIZER_PROMPT = textwrap.dedent("""\
You are a conversation summarizer for the MAYA AI assistant.

Given a conversation, produce a JSON object with EXACTLY these fields:
{
    "summary": "<2-4 sentence summary of the conversation>",
    "key_topics": ["topic1", "topic2"],
    "important_facts": ["fact1", "fact2"],
    "projects": ["project names mentioned or worked on"],
    "decisions": ["decisions made during the conversation"],
    "todos": ["action items or todos identified"]
}

RULES:
1. Output ONLY valid JSON. No markdown fences, no explanation.
2. Be concise. Each fact/topic should be one clear sentence or phrase.
3. Focus on information that would be useful to recall in future conversations.
4. Capture user preferences, project details, and recurring patterns.
5. If a field has no items, use an empty list [].
""")

_MEMORY_EXTRACTION_PROMPT = textwrap.dedent("""\
You are a memory extraction system for the MAYA AI assistant.

Given a conversation, extract memories worth keeping long-term.
Each memory must have a category, content, and importance score (0.0-1.0).

Categories: projects, people, preferences, goals, facts, skills, recurring_tasks, decisions

Output a JSON array of memory objects:
[
    {
        "category": "projects",
        "content": "User is working on Project X using Python",
        "importance": 0.85,
        "tags": ["project-x", "python"]
    }
]

RULES:
1. Output ONLY a valid JSON array. No markdown, no explanation.
2. Only include memories with importance >= 0.7.
3. Be specific — "user prefers dark mode" not "user has preferences".
4. Include tags for retrieval.
5. If nothing is worth remembering, return [].
""")


def _extract_json_object(raw: str) -> str:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    if start == -1:
        return raw

    decoder = json.JSONDecoder()
    try:
        _, end_idx = decoder.raw_decode(raw, start)
        return raw[start:end_idx]
    except (json.JSONDecodeError, ValueError):
        pass

    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
    return raw[start:]


def _extract_json_array(raw: str) -> str:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("[")
    if start == -1:
        return "[]"

    decoder = json.JSONDecoder()
    try:
        _, end_idx = decoder.raw_decode(raw, start)
        return raw[start:end_idx]
    except (json.JSONDecodeError, ValueError):
        pass

    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "[":
            depth += 1
        elif raw[i] == "]":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
    return raw[start:]


class ChatSummarizer:
    """Generates chat summaries and extracts long-term memories."""

    def summarize_chat(
        self,
        chat_id: str,
        messages: list[ChatMessage],
    ) -> ChatSummary:
        """Produce a ChatSummary from a list of messages."""
        conversation_text = self._messages_to_text(messages)

        try:
            raw = self._call_llm(
                _SUMMARIZER_PROMPT, f"CONVERSATION:\n{conversation_text}"
            )
            json_str = _extract_json_object(raw)
            data = json.loads(json_str)
        except Exception:
            data = self._fallback_summary(messages)

        summary = ChatSummary(
            chat_id=chat_id,
            summary=data.get("summary", ""),
            key_topics=data.get("key_topics", []),
            important_facts=data.get("important_facts", []),
            projects=data.get("projects", []),
            decisions=data.get("decisions", []),
            todos=data.get("todos", []),
            message_count=len(messages),
        )

        self._save_summary(summary)
        return summary

    def extract_memories(
        self,
        messages: list[ChatMessage],
        chat_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Extract long-term memories from conversation messages."""
        conversation_text = self._messages_to_text(messages)

        try:
            raw = self._call_llm(
                _MEMORY_EXTRACTION_PROMPT,
                f"CONVERSATION:\n{conversation_text}",
            )
            json_str = _extract_json_array(raw)
            memories = json.loads(json_str)
        except Exception:
            memories = []

        for mem in memories:
            mem["id"] = uuid.uuid4().hex[:12]
            if chat_id:
                mem["source_chat_id"] = chat_id

        return memories

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        client = ollama.Client(host=MEMORY_OLLAMA_BASE_URL)
        response = client.chat(
            model=SUMMARIZER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={
                "temperature": SUMMARIZER_TEMPERATURE,
                "num_ctx": SUMMARIZER_NUM_CTX,
            },
        )
        return response.message.content or ""

    def _messages_to_text(self, messages: list[ChatMessage]) -> str:
        lines: list[str] = []
        for m in messages:
            lines.append(f"{m.role.value}: {m.content}")
        return "\n".join(lines)

    def _fallback_summary(self, messages: list[ChatMessage]) -> dict[str, Any]:
        user_msgs = [m.content for m in messages if m.role.value == "user"]
        topics = list({w for msg in user_msgs[:5] for w in msg.split()[:3]})
        return {
            "summary": f"Conversation with {len(messages)} messages.",
            "key_topics": topics[:5],
            "important_facts": [],
            "projects": [],
            "decisions": [],
            "todos": [],
        }

    def _save_summary(self, summary: ChatSummary) -> None:
        ensure_dirs()
        path = CHAT_SUMMARIES_DIR / f"{summary.chat_id}_summary.json"
        path.write_text(
            json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
