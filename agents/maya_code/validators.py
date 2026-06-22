"""Safety validators for Maya Code Agent.

Every file path and command produced by an LLM passes through these checks
*before* any I/O or subprocess call.  Failures raise ``ValidationError``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from agents.maya_code import config


class ValidationError(Exception):
    """Raised when a validator rejects an input."""


# ── path safety ───────────────────────────────────────────────────────────────

def validate_project_root(root: Optional[str]) -> Path:
    """Return a resolved Path for *root*, or raise if missing/invalid."""
    if not root or not root.strip():
        raise ValidationError("project_root is required — the agent never guesses a working directory")

    resolved = Path(root).resolve()
    if not resolved.is_dir():
        raise ValidationError(f"project_root does not exist or is not a directory: {resolved}")

    maya_root = config.PROJECT_ROOT.resolve()
    if resolved == maya_root or maya_root in resolved.parents or resolved in maya_root.parents:
        if resolved != maya_root:
            pass
        else:
            raise ValidationError(
                "project_root must not be Maya's own install directory"
            )

    return resolved


def validate_path_in_root(target: str, project_root: Path) -> Path:
    """Resolve *target* and confirm it stays inside *project_root*.

    Rejects:
    - Absolute paths outside project_root
    - ``..`` traversal that escapes
    - Symlinks whose real target is outside
    """
    if not target or not target.strip():
        raise ValidationError("Empty file path")

    candidate = Path(target)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (project_root / candidate).resolve()

    root_resolved = project_root.resolve()

    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValidationError(
            f"Path escapes project root: {target!r} resolves to {resolved}, "
            f"which is outside {root_resolved}"
        )

    if resolved.is_symlink():
        real = resolved.resolve()
        if real != root_resolved and root_resolved not in real.parents:
            raise ValidationError(
                f"Symlink {target!r} points outside project root: {real}"
            )

    return resolved


def validate_file_size(content: str) -> None:
    """Reject content that exceeds the configured max file size."""
    size = len(content.encode("utf-8", errors="replace"))
    if size > config.MAX_FILE_SIZE:
        raise ValidationError(
            f"File content is {size} bytes, exceeding limit of {config.MAX_FILE_SIZE}"
        )


# ── command safety ────────────────────────────────────────────────────────────

def validate_command(command: str, project_root: Path) -> str:
    """Check *command* against the allow/deny lists and return it sanitized."""
    if not command or not command.strip():
        raise ValidationError("Empty command")

    cmd = command.strip()

    for denied in config.COMMAND_DENYLIST:
        if denied.lower() in cmd.lower():
            raise ValidationError(f"Blocked command (matches denylist): {cmd!r}")

    first_token = re.split(r'\s+', cmd)[0].lower()
    first_token_base = Path(first_token).stem.lower()

    allowed = False
    for prefix in config.COMMAND_ALLOWLIST_PREFIXES:
        prefix_parts = prefix.lower().split()
        if first_token_base == prefix_parts[0] or first_token == prefix_parts[0]:
            allowed = True
            break

    if not allowed:
        raise ValidationError(
            f"Command not in allowlist: {first_token!r}. "
            f"Allowed prefixes: {', '.join(config.COMMAND_ALLOWLIST_PREFIXES[:10])}..."
        )

    return cmd


def validate_target_exists(target: str, project_root: Path) -> Path:
    """Like validate_path_in_root but also asserts the path exists on disk."""
    resolved = validate_path_in_root(target, project_root)
    if not resolved.exists():
        raise ValidationError(f"Target does not exist: {target!r} (resolved: {resolved})")
    return resolved


def validate_not_maya_dir(path: Path) -> None:
    """Hard block: never operate inside Maya's own directory tree."""
    maya_root = config.PROJECT_ROOT.resolve()
    resolved = path.resolve()
    if resolved == maya_root or maya_root in resolved.parents:
        raise ValidationError(
            f"Refusing to operate inside Maya's install directory: {resolved}"
        )
