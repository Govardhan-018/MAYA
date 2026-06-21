"""Agent history — records every agent execution for recall and analytics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from memory.config import AGENT_HISTORY_DIR, AGENT_HISTORY_LIMIT, ensure_dirs
from memory.schemas import AgentHistoryEntry


class AgentHistory:
    """Append-only JSONL log of agent executions, plus in-memory recent cache."""

    def __init__(self) -> None:
        self._recent: list[AgentHistoryEntry] = []
        self._file: Optional[Path] = None

    def _get_file(self) -> Path:
        if self._file is None:
            ensure_dirs()
            month = datetime.now(tz=timezone.utc).strftime("%Y-%m")
            self._file = AGENT_HISTORY_DIR / f"agent_history_{month}.jsonl"
        return self._file

    def record(
        self,
        agent: str,
        action: str,
        parameters: dict[str, Any],
        status: str = "success",
        result_summary: str = "",
        duration_ms: float = 0.0,
        chat_id: Optional[str] = None,
    ) -> None:
        entry = AgentHistoryEntry(
            agent=agent,
            action=action,
            parameters=parameters,
            status=status,
            result_summary=result_summary,
            duration_ms=duration_ms,
            chat_id=chat_id,
        )
        self._recent.append(entry)
        if len(self._recent) > AGENT_HISTORY_LIMIT * 2:
            self._recent = self._recent[-AGENT_HISTORY_LIMIT:]

        line = json.dumps(entry.model_dump(mode="json"), ensure_ascii=False, default=str)
        path = self._get_file()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def get_recent(self, limit: int = AGENT_HISTORY_LIMIT) -> list[AgentHistoryEntry]:
        return list(self._recent[-limit:])

    def get_by_agent(self, agent: str, limit: int = 10) -> list[AgentHistoryEntry]:
        return [e for e in reversed(self._recent) if e.agent == agent][:limit]

    def get_recent_as_text(self, limit: int = 10) -> str:
        entries = self.get_recent(limit)
        lines: list[str] = []
        for e in entries:
            lines.append(
                f"[{e.timestamp.strftime('%H:%M')}] {e.agent}.{e.action} → {e.status}"
            )
            if e.result_summary:
                lines.append(f"  {e.result_summary[:100]}")
        return "\n".join(lines)

    def load_recent_from_disk(self, limit: int = AGENT_HISTORY_LIMIT) -> None:
        """Load recent entries from the current month's file."""
        path = self._get_file()
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        entries: list[AgentHistoryEntry] = []
        for line in lines[-limit:]:
            if line.strip():
                try:
                    data = json.loads(line)
                    entries.append(AgentHistoryEntry.model_validate(data))
                except Exception:
                    continue
        self._recent = entries

    def get_stats(self) -> dict[str, Any]:
        agents: dict[str, int] = {}
        for e in self._recent:
            agents[e.agent] = agents.get(e.agent, 0) + 1
        return {
            "total_recent": len(self._recent),
            "agents": agents,
        }
