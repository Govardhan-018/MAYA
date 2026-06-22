"""Configuration for the Memory Layer."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# ── directories ───────────────────────────────────────────────────────────
MEMORY_DIR: Path = PROJECT_ROOT / "memory"
ACTIVE_CHAT_DIR: Path = MEMORY_DIR / "active_chat"
ARCHIVE_DIR: Path = MEMORY_DIR / "archive"
CHAT_SUMMARIES_DIR: Path = MEMORY_DIR / "chat_summaries"
LONG_TERM_DIR: Path = MEMORY_DIR / "long_term"
AGENT_HISTORY_DIR: Path = MEMORY_DIR / "agent_history"
PLANNER_HISTORY_DIR: Path = MEMORY_DIR / "planner_history"
VECTORS_DIR: Path = MEMORY_DIR / "vectors"

BRAIN_STATE_PATH: Path = MEMORY_DIR / "brain_state.json"
LONG_TERM_MEMORY_PATH: Path = LONG_TERM_DIR / "long_term_memory.json"

ALL_DIRS: list[Path] = [
    MEMORY_DIR,
    ACTIVE_CHAT_DIR,
    ARCHIVE_DIR,
    CHAT_SUMMARIES_DIR,
    LONG_TERM_DIR,
    AGENT_HISTORY_DIR,
    PLANNER_HISTORY_DIR,
    VECTORS_DIR,
]

# ── chat rotation thresholds ──────────────────────────────────────────────
MAX_MESSAGES: int = int(os.getenv("MEMORY_MAX_MESSAGES", "200"))
MAX_TOKENS: int = int(os.getenv("MEMORY_MAX_TOKENS", "50000"))

# ── summarizer ────────────────────────────────────────────────────────────
_MASTER_MODEL: str = os.getenv("MAYA_MODEL", "qwen3:8b")
SUMMARIZER_MODEL: str = os.getenv("MEMORY_SUMMARIZER_MODEL", _MASTER_MODEL)
SUMMARIZER_TEMPERATURE: float = float(
    os.getenv("MEMORY_SUMMARIZER_TEMPERATURE", "0.3")
)
SUMMARIZER_NUM_CTX: int = int(os.getenv("MEMORY_SUMMARIZER_NUM_CTX", "8192"))

# ── importance scoring ────────────────────────────────────────────────────
IMPORTANCE_THRESHOLD: float = float(
    os.getenv("MEMORY_IMPORTANCE_THRESHOLD", "0.7")
)

# ── vector memory ─────────────────────────────────────────────────────────
VECTOR_COLLECTION_NAME: str = os.getenv(
    "MEMORY_VECTOR_COLLECTION", "maya_memory"
)
VECTOR_TOP_K: int = int(os.getenv("MEMORY_VECTOR_TOP_K", "5"))

# ── context builder ──────────────────────────────────────────────────────
CONTEXT_MAX_TOKENS: int = int(os.getenv("MEMORY_CONTEXT_MAX_TOKENS", "4000"))
RECENT_MESSAGES_LIMIT: int = int(
    os.getenv("MEMORY_RECENT_MESSAGES", "10")
)
AGENT_HISTORY_LIMIT: int = int(
    os.getenv("MEMORY_AGENT_HISTORY_LIMIT", "20")
)

# ── Ollama ────────────────────────────────────────────────────────────────
MEMORY_OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def ensure_dirs() -> None:
    """Create all memory directories if they don't exist."""
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)
