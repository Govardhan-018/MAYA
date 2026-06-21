"""Centralised configuration for the Brain Core."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR: Path = PROJECT_ROOT / "agents"
SYSTEM_DIR: Path = PROJECT_ROOT / "system"
LOGS_DIR: Path = PROJECT_ROOT / "brain" / "logs"

AGENT_REGISTRY_PATH: Path = SYSTEM_DIR / "agent_registry.json"
ACTION_REGISTRY_PATH: Path = SYSTEM_DIR / "action_registry.json"
PLANNER_CONTEXT_PATH: Path = SYSTEM_DIR / "planner_context.json"
CAPABILITIES_PATH: Path = SYSTEM_DIR / "agent_capabilities.json"

# ── Ollama ─────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Planner model (cloud-first, fast reasoning)
PLANNER_MODEL: str = os.getenv("PLANNER_MODEL", "qwen3:8b")
PLANNER_LOCAL_FALLBACK: str = os.getenv("PLANNER_LOCAL_FALLBACK", "qwen3:8b")

# Response model (conversational — defaults to same as planner so it works out
# of the box; override via env var if a larger model is available)
RESPONSE_MODEL: str = os.getenv("RESPONSE_MODEL", "qwen3:8b")
RESPONSE_LOCAL_FALLBACK: str = os.getenv("RESPONSE_LOCAL_FALLBACK", "qwen3:8b")

# ── execution ──────────────────────────────────────────────────────────────
MAX_WORKERS: int = int(os.getenv("BRAIN_MAX_WORKERS", "4"))
TASK_TIMEOUT_SECONDS: int = int(os.getenv("BRAIN_TASK_TIMEOUT", "30"))
TASK_MAX_RETRIES: int = int(os.getenv("BRAIN_TASK_RETRIES", "2"))
PLANNER_MAX_RETRIES: int = int(os.getenv("BRAIN_PLANNER_RETRIES", "2"))
RESPONSE_MAX_RETRIES: int = int(os.getenv("BRAIN_RESPONSE_RETRIES", "2"))

# ── LLM parameters ────────────────────────────────────────────────────────
PLANNER_NUM_CTX: int = int(os.getenv("PLANNER_NUM_CTX", "8192"))
RESPONSE_NUM_CTX: int = int(os.getenv("RESPONSE_NUM_CTX", "16384"))
PLANNER_TEMPERATURE: float = float(os.getenv("PLANNER_TEMPERATURE", "0.3"))
RESPONSE_TEMPERATURE: float = float(os.getenv("RESPONSE_TEMPERATURE", "0.7"))
