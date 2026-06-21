"""Recovery system — saves and restores Brain state across crashes/restarts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from memory.config import BRAIN_STATE_PATH, ensure_dirs
from memory.schemas import BrainState


class RecoveryManager:
    """Manages brain_state.json for crash recovery."""

    def __init__(self) -> None:
        self._state: Optional[BrainState] = None

    @property
    def state(self) -> BrainState:
        if self._state is None:
            self.load()
        assert self._state is not None
        return self._state

    def load(self) -> BrainState:
        ensure_dirs()
        if BRAIN_STATE_PATH.exists():
            try:
                data = json.loads(
                    BRAIN_STATE_PATH.read_text(encoding="utf-8")
                )
                self._state = BrainState.model_validate(data)
            except Exception:
                self._state = BrainState()
                self._save()
        else:
            self._state = BrainState()
            self._save()
        return self._state

    def _save(self) -> None:
        ensure_dirs()
        self.state.last_updated = datetime.now(tz=timezone.utc)
        BRAIN_STATE_PATH.write_text(
            json.dumps(
                self.state.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

    def save_active_chat(self, chat_id: str) -> None:
        self.state.active_chat_id = chat_id
        self._save()

    def save_current_project(self, project: Optional[str]) -> None:
        self.state.current_project = project
        self._save()

    def save_unfinished_tasks(self, tasks: list[dict[str, Any]]) -> None:
        self.state.unfinished_tasks = tasks
        self._save()

    def save_queue_state(self, queue_state: dict[str, Any]) -> None:
        self.state.queue_state = queue_state
        self._save()

    def save_planner_state(self, planner_state: dict[str, Any]) -> None:
        self.state.planner_state = planner_state
        self._save()

    def clear_unfinished_tasks(self) -> None:
        self.state.unfinished_tasks = []
        self._save()

    def clear_queue_state(self) -> None:
        self.state.queue_state = {}
        self._save()

    def get_recovery_info(self) -> dict[str, Any]:
        """Return a summary of what can be recovered."""
        return {
            "has_active_chat": self.state.active_chat_id is not None,
            "active_chat_id": self.state.active_chat_id,
            "current_project": self.state.current_project,
            "unfinished_task_count": len(self.state.unfinished_tasks),
            "has_queue_state": bool(self.state.queue_state),
            "has_planner_state": bool(self.state.planner_state),
            "last_updated": self.state.last_updated.isoformat(),
        }

    def full_save(
        self,
        *,
        chat_id: Optional[str] = None,
        project: Optional[str] = None,
        unfinished_tasks: Optional[list[dict[str, Any]]] = None,
        queue_state: Optional[dict[str, Any]] = None,
        planner_state: Optional[dict[str, Any]] = None,
    ) -> None:
        """Bulk update all state fields at once."""
        if chat_id is not None:
            self.state.active_chat_id = chat_id
        if project is not None:
            self.state.current_project = project
        if unfinished_tasks is not None:
            self.state.unfinished_tasks = unfinished_tasks
        if queue_state is not None:
            self.state.queue_state = queue_state
        if planner_state is not None:
            self.state.planner_state = planner_state
        self._save()
