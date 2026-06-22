"""Checkpoint manager — backup + rollback for file operations.

Before every file write/modify/delete the runner calls ``save()``, which
snapshots the file (or records its absence).  ``rollback()`` restores
every file to its pre-job state.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agents.maya_code import config


@dataclass
class _Entry:
    path: Path
    existed: bool
    backup_path: Optional[Path] = None


class CheckpointManager:
    """Per-job checkpoint with full rollback capability."""

    def __init__(self, job_id: str, project_root: Path) -> None:
        self._job_id = job_id
        self._project_root = project_root
        self._dir = project_root / config.CHECKPOINT_DIR_NAME / job_id
        self._entries: dict[str, _Entry] = {}
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, target: Path) -> None:
        """Snapshot *target* before it gets modified/created/deleted."""
        key = str(target.resolve())
        if key in self._entries:
            return  # already backed up

        existed = target.exists()
        backup: Optional[Path] = None

        if existed and target.is_file():
            backup = self._dir / f"{len(self._entries)}_{target.name}"
            shutil.copy2(str(target), str(backup))

        self._entries[key] = _Entry(
            path=target.resolve(),
            existed=existed,
            backup_path=backup,
        )

    def rollback(self) -> list[str]:
        """Restore all checkpointed files to pre-job state.  Returns log lines."""
        log: list[str] = []

        for key, entry in reversed(list(self._entries.items())):
            try:
                if entry.existed and entry.backup_path and entry.backup_path.exists():
                    shutil.copy2(str(entry.backup_path), str(entry.path))
                    log.append(f"Restored: {entry.path}")
                elif not entry.existed and entry.path.exists():
                    entry.path.unlink()
                    log.append(f"Removed (was new): {entry.path}")
                    parent = entry.path.parent
                    if parent != self._project_root and parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()
                        log.append(f"Removed empty dir: {parent}")
            except Exception as exc:
                log.append(f"Rollback error for {entry.path}: {exc}")

        return log

    def cleanup(self) -> None:
        """Remove checkpoint directory for this job."""
        try:
            if self._dir.exists():
                shutil.rmtree(str(self._dir))
            parent = self._dir.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass

    @property
    def entry_count(self) -> int:
        return len(self._entries)
