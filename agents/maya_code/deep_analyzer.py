"""v2 Deep Analyzer — reads actual file contents to build rich project context.

Unlike the v1 analyzer (which only scans names/extensions), this reads entry
points, dependency files, and key files to understand architecture, imports,
and code patterns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agents.maya_code import config
from agents.maya_code.contracts import ParsedGoal, ProjectAnalysis
from agents.maya_code.validators import validate_path_in_root, ValidationError


def deep_analyze(
    project_root: Path,
    analysis: ProjectAnalysis,
    parsed_goal: ParsedGoal,
) -> str:
    """Read key files and return formatted context for LLM consumption."""
    files_to_read: list[str] = []

    # Priority 1: dependency/config files
    for dep in analysis.dependency_files:
        if dep not in files_to_read:
            files_to_read.append(dep)

    # Priority 2: entry points
    for ep in analysis.entry_points[:5]:
        if ep not in files_to_read:
            files_to_read.append(ep)

    # Priority 3: key files from goal parsing
    for kf in parsed_goal.key_files[:10]:
        if kf not in files_to_read:
            files_to_read.append(kf)

    sections: list[str] = []
    total_chars = 0
    max_total = config.V2_MAX_FILE_READ_SIZE * 3

    for rel_path in files_to_read:
        if total_chars >= max_total:
            break

        content = _safe_read(project_root, rel_path)
        if content is None:
            continue

        budget = min(config.V2_MAX_FILE_READ_SIZE, max_total - total_chars)
        if len(content) > budget:
            content = content[:budget] + "\n... [truncated]"

        sections.append(f"### {rel_path}\n```\n{content}\n```")
        total_chars += len(content)

    if not sections:
        return "(No readable files found for deep analysis)"

    return "## Key File Contents\n\n" + "\n\n".join(sections)


def _safe_read(project_root: Path, rel_path: str) -> Optional[str]:
    """Read a file safely, returning None on any error."""
    try:
        resolved = validate_path_in_root(rel_path, project_root)
        if not resolved.exists() or not resolved.is_file():
            return None
        if resolved.stat().st_size > config.MAX_FILE_SIZE:
            return None
        return resolved.read_text(encoding="utf-8", errors="replace")
    except (ValidationError, OSError, UnicodeDecodeError):
        return None
