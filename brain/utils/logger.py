"""JSONL logging for Brain operations.

Three log streams:
    brain/logs/brain.jsonl        — top-level request lifecycle
    brain/logs/planner.jsonl      — planner calls and plans
    brain/logs/agent_calls.jsonl  — individual agent executions
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain.utils.config import LOGS_DIR

_lock = threading.Lock()


def _ensure_logs_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _append(filename: str, record: dict[str, Any]) -> None:
    """Append a single JSON record to a .jsonl file (thread-safe)."""
    _ensure_logs_dir()
    record["timestamp"] = datetime.now(tz=timezone.utc).isoformat()
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    with _lock:
        with open(LOGS_DIR / filename, "a", encoding="utf-8") as fh:
            fh.write(line)


def log_brain(event: str, **kwargs: Any) -> None:
    """Log a brain-level event."""
    _append("brain.jsonl", {"event": event, **kwargs})


def log_planner(event: str, **kwargs: Any) -> None:
    """Log a planner-level event."""
    _append("planner.jsonl", {"event": event, **kwargs})


def log_agent_call(event: str, **kwargs: Any) -> None:
    """Log an agent execution event."""
    _append("agent_calls.jsonl", {"event": event, **kwargs})
