"""Configuration for the Voice Orchestration Layer."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
VOICE_LOGS_DIR: Path = PROJECT_ROOT / "brain" / "logs"

VOICE_MODE_ENABLED: bool = os.getenv("VOICE_MODE_ENABLED", "true").lower() == "true"
ENABLE_INTERRUPTS: bool = os.getenv("ENABLE_INTERRUPTS", "true").lower() == "true"
CONVERSATION_TIMEOUT: int = int(os.getenv("CONVERSATION_TIMEOUT", "180"))
FILLER_ENABLED: bool = os.getenv("FILLER_ENABLED", "true").lower() == "true"
FILLER_INTERVAL: float = float(os.getenv("FILLER_INTERVAL", "5"))
MAX_SPEECH_QUEUE: int = int(os.getenv("MAX_SPEECH_QUEUE", "20"))
LONG_TASK_THRESHOLD: float = float(os.getenv("LONG_TASK_THRESHOLD", "5.0"))

INTERRUPT_WORDS: list[str] = [
    "stop", "cancel", "maya stop", "quiet", "silence",
    "shut up", "enough", "that's enough", "nevermind", "never mind",
]
