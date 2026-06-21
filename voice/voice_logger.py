"""JSONL logging for voice events."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from voice.config import VOICE_LOGS_DIR

_lock = threading.Lock()


def log_voice(event: str, **kwargs: Any) -> None:
    VOICE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "event": event,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        **kwargs,
    }
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    with _lock:
        with open(VOICE_LOGS_DIR / "voice.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line)
