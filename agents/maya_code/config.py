"""Environment-driven configuration for Maya Code Agent.

Every tunable is loaded from os.environ with a sensible default so the agent
works out of the box without a .env entry.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── feature flags ─────────────────────────────────────────────────────────────
ENABLED: bool = os.getenv("MAYA_CODE_AGENT_ENABLED", "true").lower() in ("true", "1", "yes")

# ── LLM model chain (primary → fallback → fallback_2) ────────────────────────
_MASTER_MODEL: str = os.getenv("MAYA_MODEL", "qwen3:8b")
MODEL_PRIMARY: str = os.getenv("MAYA_CODE_AGENT_MODEL", _MASTER_MODEL)
MODEL_FALLBACK: str = os.getenv("MAYA_CODE_AGENT_FALLBACK", _MASTER_MODEL)
MODEL_FALLBACK_2: str = os.getenv("MAYA_CODE_AGENT_FALLBACK_2", _MASTER_MODEL)
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_TEMPERATURE: float = float(os.getenv("MAYA_CODE_AGENT_TEMPERATURE", "0.2"))
LLM_NUM_CTX: int = int(os.getenv("MAYA_CODE_AGENT_NUM_CTX", "16384"))
LLM_TIMEOUT: int = int(os.getenv("MAYA_CODE_AGENT_LLM_TIMEOUT", "120"))

# ── execution bounds ─────────────────────────────────────────────────────────
MAX_ITERATIONS: int = int(os.getenv("MAYA_CODE_AGENT_MAX_ITERATIONS", "30"))
MAX_FIXES_PER_STEP: int = int(os.getenv("MAYA_CODE_AGENT_MAX_FIXES", "3"))
CONSECUTIVE_FAILURE_LIMIT: int = int(os.getenv("MAYA_CODE_AGENT_FAILURE_LIMIT", "5"))
COMMAND_TIMEOUT: int = int(os.getenv("MAYA_CODE_AGENT_CMD_TIMEOUT", "60"))
MAX_FILE_SIZE: int = int(os.getenv("MAYA_CODE_AGENT_MAX_FILE_SIZE", str(2 * 1024 * 1024)))  # 2 MB
MAX_LOG_TAIL: int = int(os.getenv("MAYA_CODE_AGENT_LOG_TAIL", "25"))
MAX_REPARSE_ATTEMPTS: int = int(os.getenv("MAYA_CODE_AGENT_REPARSE", "3"))

# ── paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
JOBS_DIR: Path = PROJECT_ROOT / "system" / "code_jobs"
LOG_FILE: Path = PROJECT_ROOT / "logs" / "maya_code_agent.jsonl"
CHECKPOINT_DIR_NAME: str = ".maya_checkpoints"

# ── command safety ────────────────────────────────────────────────────────────
COMMAND_ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "python", "python3", "pip", "pip3",
    "node", "npm", "npx", "yarn", "pnpm",
    "cargo", "rustc",
    "go", "go run", "go build", "go test",
    "dotnet",
    "javac", "java", "mvn", "gradle",
    "git",
    "pytest", "unittest", "jest", "mocha", "vitest",
    "cat", "head", "tail", "ls", "dir", "find", "grep", "rg",
    "echo", "type", "more",
    "mkdir", "touch", "cp", "copy",
    "curl", "wget",
    "make", "cmake",
    "tsc", "eslint", "prettier", "black", "ruff", "mypy", "flake8",
    "start", "open", "xdg-open",
    "powershell", "cmd",
    "ruby", "perl", "php",
    "docker", "docker-compose",
)

COMMAND_DENYLIST: tuple[str, ...] = (
    "rm -rf /", "rm -rf ~", "rm -rf .", "rm -rf ..",
    "rmdir /s /q C:", "del /s /q C:",
    "mkfs", "dd if=", "format C:",
    ":(){:|:&};:", "fork", ":(){ :|:& };:",
    "shutdown", "reboot", "halt", "poweroff",
    "chmod 777 /", "chown -R",
    "> /dev/sda", "mv / ",
    "curl | sh", "curl | bash", "wget | sh", "wget | bash",
)
