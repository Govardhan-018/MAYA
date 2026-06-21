"""Planner history — records user commands, plans, and execution results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from memory.config import PLANNER_HISTORY_DIR, ensure_dirs
from memory.schemas import PlannerHistoryEntry


class PlannerHistory:
    """Append-only JSONL log of planner invocations."""

    def __init__(self) -> None:
        self._recent: list[PlannerHistoryEntry] = []
        self._file: Optional[Path] = None

    def _get_file(self) -> Path:
        if self._file is None:
            ensure_dirs()
            month = datetime.now(tz=timezone.utc).strftime("%Y-%m")
            self._file = PLANNER_HISTORY_DIR / f"planner_history_{month}.jsonl"
        return self._file

    def record(
        self,
        user_command: str,
        plan_json: dict[str, Any],
        execution_results: list[dict[str, Any]],
        response: str = "",
        duration_ms: float = 0.0,
        chat_id: Optional[str] = None,
    ) -> None:
        entry = PlannerHistoryEntry(
            user_command=user_command,
            plan_json=plan_json,
            execution_results=execution_results,
            response=response,
            duration_ms=duration_ms,
            chat_id=chat_id,
        )
        self._recent.append(entry)
        if len(self._recent) > 50:
            self._recent = self._recent[-30:]

        line = json.dumps(entry.model_dump(mode="json"), ensure_ascii=False, default=str)
        path = self._get_file()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def get_recent(self, limit: int = 10) -> list[PlannerHistoryEntry]:
        return list(self._recent[-limit:])

    def get_recent_as_text(self, limit: int = 5) -> str:
        entries = self.get_recent(limit)
        lines: list[str] = []
        for e in entries:
            lines.append(f"Command: {e.user_command}")
            task_count = len(e.plan_json.get("tasks", []))
            lines.append(f"  Plan: {task_count} tasks, Response: {e.response[:80]}...")
        return "\n".join(lines)

    def load_recent_from_disk(self, limit: int = 30) -> None:
        path = self._get_file()
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        entries: list[PlannerHistoryEntry] = []
        for line in lines[-limit:]:
            if line.strip():
                try:
                    data = json.loads(line)
                    entries.append(PlannerHistoryEntry.model_validate(data))
                except Exception:
                    continue
        self._recent = entries
