"""v2 Tool Belt — executes individual tool calls from the agentic loop.

Each tool goes through validators before any I/O.  Results are always returned
as ``ToolResult``; exceptions are caught, never re-raised.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Optional

from agents.maya_code import config
from agents.maya_code.checkpoint import CheckpointManager
from agents.maya_code.contracts import ToolCall, ToolName, ToolResult
from agents.maya_code.validators import (
    ValidationError,
    validate_command,
    validate_file_size,
    validate_path_in_root,
)


class ToolBelt:
    """Dispatches a ``ToolCall`` to the right handler and returns a ``ToolResult``."""

    def __init__(self, project_root: Path, checkpoint: CheckpointManager) -> None:
        self._root = project_root
        self._cp = checkpoint
        self._files_created: list[str] = []
        self._files_modified: list[str] = []
        self._files_deleted: list[str] = []
        self.file_cache: dict[str, str] = {}

    @property
    def files_created(self) -> list[str]:
        return list(self._files_created)

    @property
    def files_modified(self) -> list[str]:
        return list(self._files_modified)

    @property
    def files_deleted(self) -> list[str]:
        return list(self._files_deleted)

    def execute(self, tc: ToolCall) -> ToolResult:
        try:
            handler = {
                ToolName.READ_FILE:    self._read_file,
                ToolName.WRITE_FILE:   self._write_file,
                ToolName.EDIT_FILE:    self._edit_file,
                ToolName.RUN_CMD:      self._run_cmd,
                ToolName.SEARCH_CODE:  self._search_code,
                ToolName.LIST_FILES:   self._list_files,
                ToolName.RUN_TESTS:    self._run_tests,
                ToolName.DONE:         self._done,
            }.get(tc.tool)

            if handler is None:
                return ToolResult(tool=tc.tool, success=False, error=f"Unknown tool: {tc.tool}")

            return handler(tc.args)

        except ValidationError as exc:
            return ToolResult(tool=tc.tool, success=False, error=f"Validation: {exc}")
        except Exception as exc:
            return ToolResult(tool=tc.tool, success=False, error=f"{type(exc).__name__}: {exc}")

    # ── read_file ────────────────────────────────────────────────────────────

    def _read_file(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        if not path:
            return ToolResult(tool=ToolName.READ_FILE, success=False, error="Missing 'path'")

        resolved = validate_path_in_root(path, self._root)
        if not resolved.exists():
            return ToolResult(tool=ToolName.READ_FILE, success=False,
                              error=f"File not found: {path}")
        if not resolved.is_file():
            return ToolResult(tool=ToolName.READ_FILE, success=False,
                              error=f"Not a file: {path}")

        content = resolved.read_text(encoding="utf-8", errors="replace")
        if len(content) > config.V2_MAX_FILE_READ_SIZE:
            content = content[: config.V2_MAX_FILE_READ_SIZE] + "\n... [truncated]"

        self.file_cache[path] = content
        lines = content.count("\n") + 1
        return ToolResult(tool=ToolName.READ_FILE, success=True,
                          output=content,
                          error=None)

    # ── write_file ───────────────────────────────────────────────────────────

    def _write_file(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        content = args.get("content", "")
        if not path:
            return ToolResult(tool=ToolName.WRITE_FILE, success=False, error="Missing 'path'")

        resolved = validate_path_in_root(path, self._root)
        validate_file_size(content)

        existed = resolved.exists()
        self._cp.save(resolved)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")

        if existed:
            if path not in self._files_modified and path not in self._files_created:
                self._files_modified.append(path)
        else:
            if path not in self._files_created:
                self._files_created.append(path)

        self.file_cache[path] = content
        return ToolResult(tool=ToolName.WRITE_FILE, success=True,
                          output=f"Written {len(content)} chars to {path}")

    # ── edit_file (search/replace) ───────────────────────────────────────────

    def _edit_file(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        search = args.get("search", "")
        replace = args.get("replace", "")

        if not path:
            return ToolResult(tool=ToolName.EDIT_FILE, success=False, error="Missing 'path'")
        if not search:
            return ToolResult(tool=ToolName.EDIT_FILE, success=False, error="Missing 'search'")

        resolved = validate_path_in_root(path, self._root)
        if not resolved.exists():
            return ToolResult(tool=ToolName.EDIT_FILE, success=False,
                              error=f"File not found: {path}")

        current = resolved.read_text(encoding="utf-8", errors="replace")
        count = current.count(search)

        if count == 0:
            return ToolResult(tool=ToolName.EDIT_FILE, success=False,
                              error=f"Search string not found in {path}")

        if count > 1:
            return ToolResult(tool=ToolName.EDIT_FILE, success=False,
                              error=f"Search string found {count} times in {path} — must be unique. Provide more context.")

        new_content = current.replace(search, replace, 1)
        validate_file_size(new_content)

        self._cp.save(resolved)
        resolved.write_text(new_content, encoding="utf-8")

        if path not in self._files_modified and path not in self._files_created:
            self._files_modified.append(path)

        self.file_cache[path] = new_content
        return ToolResult(tool=ToolName.EDIT_FILE, success=True,
                          output=f"Replaced 1 occurrence in {path}")

    # ── run_cmd ──────────────────────────────────────────────────────────────

    def _run_cmd(self, args: dict) -> ToolResult:
        command = args.get("command", "")
        if not command:
            return ToolResult(tool=ToolName.RUN_CMD, success=False, error="Missing 'command'")

        cmd = validate_command(command, self._root)
        return self._shell(ToolName.RUN_CMD, cmd)

    # ── search_code ──────────────────────────────────────────────────────────

    def _search_code(self, args: dict) -> ToolResult:
        pattern = args.get("pattern", "")
        glob_filter = args.get("glob", "")
        if not pattern:
            return ToolResult(tool=ToolName.SEARCH_CODE, success=False, error="Missing 'pattern'")

        is_win = platform.system() == "Windows"
        if is_win:
            cmd = f'findstr /s /n /i /c:"{pattern}" *'
            if glob_filter:
                cmd = f'findstr /s /n /i /c:"{pattern}" {glob_filter}'
        else:
            cmd = f'grep -rn --include="*" -i "{pattern}" .'
            if glob_filter:
                cmd = f'grep -rn --include="{glob_filter}" -i "{pattern}" .'

        try:
            result = subprocess.run(
                cmd, shell=True, cwd=str(self._root),
                capture_output=True, text=True,
                timeout=config.COMMAND_TIMEOUT,
            )
            lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
            limited = lines[: config.V2_SEARCH_RESULTS_LIMIT]
            output = "\n".join(limited)
            if len(lines) > config.V2_SEARCH_RESULTS_LIMIT:
                output += f"\n... ({len(lines) - config.V2_SEARCH_RESULTS_LIMIT} more)"

            return ToolResult(tool=ToolName.SEARCH_CODE, success=True,
                              output=output or "No matches found")
        except subprocess.TimeoutExpired:
            return ToolResult(tool=ToolName.SEARCH_CODE, success=False,
                              error=f"Search timed out after {config.COMMAND_TIMEOUT}s")

    # ── list_files ───────────────────────────────────────────────────────────

    def _list_files(self, args: dict) -> ToolResult:
        subpath = args.get("path", ".")
        resolved = validate_path_in_root(subpath, self._root) if subpath != "." else self._root

        if not resolved.exists():
            return ToolResult(tool=ToolName.LIST_FILES, success=False,
                              error=f"Path not found: {subpath}")
        if not resolved.is_dir():
            return ToolResult(tool=ToolName.LIST_FILES, success=False,
                              error=f"Not a directory: {subpath}")

        skip = {"node_modules", ".git", "__pycache__", ".maya_checkpoints", ".venv", "venv"}
        entries: list[str] = []
        try:
            for item in sorted(resolved.iterdir()):
                if item.name in skip:
                    continue
                prefix = "d " if item.is_dir() else "f "
                rel = item.relative_to(self._root)
                entries.append(f"{prefix}{rel}")
                if len(entries) >= 100:
                    entries.append("... (truncated)")
                    break
        except PermissionError:
            return ToolResult(tool=ToolName.LIST_FILES, success=False,
                              error=f"Permission denied: {subpath}")

        return ToolResult(tool=ToolName.LIST_FILES, success=True,
                          output="\n".join(entries) or "(empty directory)")

    # ── run_tests ────────────────────────────────────────────────────────────

    def _run_tests(self, args: dict) -> ToolResult:
        command = args.get("command", "")
        if not command:
            return ToolResult(tool=ToolName.RUN_TESTS, success=False, error="Missing 'command'")

        cmd = validate_command(command, self._root)
        return self._shell(ToolName.RUN_TESTS, cmd)

    # ── done (signal subtask completion) ─────────────────────────────────────

    def _done(self, args: dict) -> ToolResult:
        summary = args.get("summary", "Subtask completed")
        return ToolResult(tool=ToolName.DONE, success=True, output=summary)

    # ── subprocess helper ────────────────────────────────────────────────────

    def _shell(self, tool: ToolName, cmd: str) -> ToolResult:
        try:
            result = subprocess.run(
                cmd, shell=True, cwd=str(self._root),
                capture_output=True, text=True,
                timeout=config.COMMAND_TIMEOUT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            success = result.returncode == 0
            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout[-4000:])
            if result.stderr:
                output_parts.append(f"[stderr] {result.stderr[-2000:]}")
            output = "\n".join(output_parts) or "(no output)"

            return ToolResult(
                tool=tool, success=success, output=output,
                error=None if success else f"Exit code {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(tool=tool, success=False,
                              error=f"Command timed out after {config.COMMAND_TIMEOUT}s")
