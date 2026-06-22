"""Step executor — carries out individual plan steps.

Every step passes through validators before any I/O or subprocess call.
Results are always returned as ``StepResult``; exceptions are caught and
converted to error results, never re-raised.
"""

from __future__ import annotations

import os
import platform
import subprocess
import traceback
from pathlib import Path
from typing import Optional

from agents.maya_code import config
from agents.maya_code.checkpoint import CheckpointManager
from agents.maya_code.contracts import PlanStep, StepAction, StepResult
from agents.maya_code.validators import (
    ValidationError,
    validate_command,
    validate_file_size,
    validate_path_in_root,
)


class StepExecutor:
    """Executes a single ``PlanStep`` inside a validated project root."""

    def __init__(self, project_root: Path, checkpoint: CheckpointManager, *, dry_run: bool = False) -> None:
        self._root = project_root
        self._cp = checkpoint
        self._dry_run = dry_run
        self._files_created: list[str] = []
        self._files_modified: list[str] = []
        self._files_deleted: list[str] = []

    @property
    def files_created(self) -> list[str]:
        return list(self._files_created)

    @property
    def files_modified(self) -> list[str]:
        return list(self._files_modified)

    @property
    def files_deleted(self) -> list[str]:
        return list(self._files_deleted)

    def execute_step(self, step: PlanStep) -> StepResult:
        """Dispatch to the right handler based on ``step.action``."""
        try:
            handler = {
                StepAction.CREATE_FILE:  self._create_file,
                StepAction.MODIFY_FILE:  self._modify_file,
                StepAction.DELETE_FILE:  self._delete_file,
                StepAction.RUN_COMMAND:  self._run_command,
                StepAction.INSTALL_DEPS: self._install_deps,
                StepAction.RUN_TESTS:   self._run_tests,
            }.get(step.action)

            if handler is None:
                return StepResult(
                    step_id=step.id,
                    success=False,
                    action=step.action,
                    error=f"Unknown action: {step.action}",
                )

            return handler(step)

        except ValidationError as exc:
            return StepResult(
                step_id=step.id, success=False, action=step.action,
                target=step.target, error=f"Validation: {exc}",
            )
        except Exception as exc:
            return StepResult(
                step_id=step.id, success=False, action=step.action,
                target=step.target, error=f"{type(exc).__name__}: {exc}",
            )

    # ── handlers ──────────────────────────────────────────────────────────────

    def _create_file(self, step: PlanStep) -> StepResult:
        resolved = validate_path_in_root(step.target, self._root)
        content = step.content or ""
        validate_file_size(content)

        if self._dry_run:
            return StepResult(step_id=step.id, success=True, action=step.action,
                              target=step.target, stdout="[dry-run] would create file")

        self._cp.save(resolved)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        self._files_created.append(step.target)

        return StepResult(step_id=step.id, success=True, action=step.action,
                          target=step.target, stdout=f"Created {step.target}")

    def _modify_file(self, step: PlanStep) -> StepResult:
        resolved = validate_path_in_root(step.target, self._root)
        if not resolved.exists():
            return StepResult(step_id=step.id, success=False, action=step.action,
                              target=step.target, error=f"File not found: {step.target}")

        content = step.content or ""
        validate_file_size(content)

        if self._dry_run:
            return StepResult(step_id=step.id, success=True, action=step.action,
                              target=step.target, stdout="[dry-run] would modify file")

        self._cp.save(resolved)
        resolved.write_text(content, encoding="utf-8")
        self._files_modified.append(step.target)

        return StepResult(step_id=step.id, success=True, action=step.action,
                          target=step.target, stdout=f"Modified {step.target}")

    def _delete_file(self, step: PlanStep) -> StepResult:
        resolved = validate_path_in_root(step.target, self._root)
        if not resolved.exists():
            return StepResult(step_id=step.id, success=True, action=step.action,
                              target=step.target, stdout="Already absent")

        if self._dry_run:
            return StepResult(step_id=step.id, success=True, action=step.action,
                              target=step.target, stdout="[dry-run] would delete file")

        self._cp.save(resolved)
        resolved.unlink()
        self._files_deleted.append(step.target)

        return StepResult(step_id=step.id, success=True, action=step.action,
                          target=step.target, stdout=f"Deleted {step.target}")

    def _run_command(self, step: PlanStep) -> StepResult:
        if not step.command:
            return StepResult(step_id=step.id, success=False, action=step.action,
                              error="No command specified")

        cmd = validate_command(step.command, self._root)

        if self._dry_run:
            return StepResult(step_id=step.id, success=True, action=step.action,
                              target=step.target, stdout=f"[dry-run] would run: {cmd}")

        return self._shell(step.id, step.action, cmd)

    def _install_deps(self, step: PlanStep) -> StepResult:
        if not step.command:
            return StepResult(step_id=step.id, success=False, action=step.action,
                              error="No install command specified")

        cmd = validate_command(step.command, self._root)

        if self._dry_run:
            return StepResult(step_id=step.id, success=True, action=step.action,
                              stdout=f"[dry-run] would install: {cmd}")

        return self._shell(step.id, step.action, cmd)

    def _run_tests(self, step: PlanStep) -> StepResult:
        if not step.command:
            return StepResult(step_id=step.id, success=False, action=step.action,
                              error="No test command specified")

        cmd = validate_command(step.command, self._root)

        if self._dry_run:
            return StepResult(step_id=step.id, success=True, action=step.action,
                              stdout=f"[dry-run] would test: {cmd}")

        return self._shell(step.id, step.action, cmd)

    # ── subprocess helper ────────────────────────────────────────────────────

    def _shell(self, step_id: int, action: StepAction, cmd: str) -> StepResult:
        """Run *cmd* in a subprocess jailed to project_root."""
        try:
            is_win = platform.system() == "Windows"
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=config.COMMAND_TIMEOUT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            success = result.returncode == 0
            return StepResult(
                step_id=step_id, success=success, action=action,
                stdout=result.stdout[-4000:] if result.stdout else "",
                stderr=result.stderr[-2000:] if result.stderr else "",
                error=None if success else f"Exit code {result.returncode}",
            )

        except subprocess.TimeoutExpired:
            return StepResult(
                step_id=step_id, success=False, action=action,
                error=f"Command timed out after {config.COMMAND_TIMEOUT}s",
            )
        except Exception as exc:
            return StepResult(
                step_id=step_id, success=False, action=action,
                error=f"Subprocess error: {exc}",
            )
