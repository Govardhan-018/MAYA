"""todo_agent.py — Persistent todo management plugin (TOOL ONLY).

This module is a *pure tool*. It performs **no** analysis, prioritization,
reasoning, recommendations, scheduling decisions, intent detection,
productivity advice, or task classification. It only:

    1. Receives a JSON-compatible ``dict`` request.
    2. Stores, updates, retrieves, or deletes todos in a local JSON file.
    3. Returns a JSON-compatible ``dict`` response.

All intelligence belongs to the calling "Brain Agent". The single public
entry point is :func:`execute`.

Dependencies: Python standard library only (no third-party packages).

Storage: ``data/todos.json`` (created automatically on first write).

CLI usage::

    python todo_agent.py request.json
    python todo_agent.py '{"action": "list_all_todos", "parameters": {}}'
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

__all__ = ["execute", "PLUGIN_INFO"]


# --------------------------------------------------------------------------- #
# Plugin metadata
# --------------------------------------------------------------------------- #
PLUGIN_INFO: dict[str, str] = {
    "name": "todo_agent",
    "agent_name": "TodoAgent",
    "version": "1.0.0",
    "type": "tool",
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
    "description": "Persistent todo management plugin",
}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
_BASE_DIR: Path = Path(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR: Path = _BASE_DIR / "data"
_TODOS_FILE: Path = _DATA_DIR / "todos.json"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class TodoAgentError(Exception):
    """Raised for any handled error whose message is safe to return.

    Covers parameter validation, missing todos, and storage failures.
    These map to a structured ``status: error`` response instead of
    crashing the tool.
    """


# --------------------------------------------------------------------------- #
# Persistence layer
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def _load_todos() -> list[dict[str, Any]]:
    """Load the todo list from disk, returning an empty list if absent."""
    if not _TODOS_FILE.exists():
        return []
    try:
        raw = _TODOS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data.get("todos", [])
        return []
    except (json.JSONDecodeError, OSError) as exc:
        raise TodoAgentError(f"Failed to read todos file: {exc}")


def _save_todos(todos: list[dict[str, Any]]) -> None:
    """Persist the todo list to disk atomically (write-then-rename)."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _TODOS_FILE.with_suffix(".tmp")
    try:
        payload = json.dumps({"todos": todos}, indent=2, ensure_ascii=False, default=str)
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(_TODOS_FILE)
    except OSError as exc:
        raise TodoAgentError(f"Failed to save todos: {exc}")


def _find_todo(todos: list[dict[str, Any]], todo_id: str) -> tuple[int, dict[str, Any]]:
    """Return the index and dict for *todo_id*, or raise."""
    for i, todo in enumerate(todos):
        if todo.get("id") == todo_id:
            return i, todo
    raise TodoAgentError("Todo not found")


def _make_todo(
    title: str,
    description: str = "",
    tags: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a new todo dict with generated id and timestamps."""
    now = _now_iso()
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "tags": tags or [],
        "metadata": metadata or {},
    }


# --------------------------------------------------------------------------- #
# Action handlers
# --------------------------------------------------------------------------- #
def _action_add_todo(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title", "")
    if not title or not str(title).strip():
        raise TodoAgentError("Title is required")
    todo = _make_todo(
        title=str(title).strip(),
        description=str(params.get("description", "")).strip(),
        tags=params.get("tags"),
        metadata=params.get("metadata"),
    )
    todos = _load_todos()
    todos.append(todo)
    _save_todos(todos)
    return {"todo": todo}


def _action_update_todo(params: dict[str, Any]) -> dict[str, Any]:
    todo_id = params.get("id", "")
    if not todo_id:
        raise TodoAgentError("Missing todo id")
    todos = _load_todos()
    idx, todo = _find_todo(todos, todo_id)

    updated = False
    for key in ("title", "description", "tags", "metadata"):
        if key in params:
            value = params[key]
            if key == "title":
                if not value or not str(value).strip():
                    raise TodoAgentError("Title cannot be empty")
                value = str(value).strip()
            elif key == "description":
                value = str(value).strip()
            todo[key] = value
            updated = True

    if not updated:
        raise TodoAgentError("No fields to update (provide title, description, tags, or metadata)")

    todo["updated_at"] = _now_iso()
    todos[idx] = todo
    _save_todos(todos)
    return {"todo": todo}


def _action_complete_todo(params: dict[str, Any]) -> dict[str, Any]:
    todo_id = params.get("id", "")
    if not todo_id:
        raise TodoAgentError("Missing todo id")
    todos = _load_todos()
    idx, todo = _find_todo(todos, todo_id)
    if todo["status"] == "completed":
        raise TodoAgentError("Todo is already completed")
    now = _now_iso()
    todo["status"] = "completed"
    todo["completed_at"] = now
    todo["updated_at"] = now
    todos[idx] = todo
    _save_todos(todos)
    return {"todo": todo}


def _action_reopen_todo(params: dict[str, Any]) -> dict[str, Any]:
    todo_id = params.get("id", "")
    if not todo_id:
        raise TodoAgentError("Missing todo id")
    todos = _load_todos()
    idx, todo = _find_todo(todos, todo_id)
    if todo["status"] == "pending":
        raise TodoAgentError("Todo is already pending")
    todo["status"] = "pending"
    todo["completed_at"] = None
    todo["updated_at"] = _now_iso()
    todos[idx] = todo
    _save_todos(todos)
    return {"todo": todo}


def _action_delete_todo(params: dict[str, Any]) -> dict[str, Any]:
    todo_id = params.get("id", "")
    if not todo_id:
        raise TodoAgentError("Missing todo id")
    todos = _load_todos()
    idx, todo = _find_todo(todos, todo_id)
    deleted = todos.pop(idx)
    _save_todos(todos)
    return {"deleted": deleted}


def _action_get_todo(params: dict[str, Any]) -> dict[str, Any]:
    todo_id = params.get("id", "")
    if not todo_id:
        raise TodoAgentError("Missing todo id")
    todos = _load_todos()
    _, todo = _find_todo(todos, todo_id)
    return {"todo": todo}


def _action_list_all_todos(params: dict[str, Any]) -> dict[str, Any]:
    todos = _load_todos()
    return {"count": len(todos), "todos": todos}


def _action_list_pending_todos(params: dict[str, Any]) -> dict[str, Any]:
    todos = _load_todos()
    pending = [t for t in todos if t.get("status") == "pending"]
    return {"count": len(pending), "todos": pending}


def _action_list_completed_todos(params: dict[str, Any]) -> dict[str, Any]:
    todos = _load_todos()
    completed = [t for t in todos if t.get("status") == "completed"]
    return {"count": len(completed), "todos": completed}


def _action_search_todos(params: dict[str, Any]) -> dict[str, Any]:
    query = params.get("query", "")
    if not query or not str(query).strip():
        raise TodoAgentError("Missing query parameter")
    query_lower = str(query).strip().lower()
    todos = _load_todos()
    matches = []
    for todo in todos:
        title = todo.get("title", "").lower()
        description = todo.get("description", "").lower()
        tags = [t.lower() for t in todo.get("tags", [])]
        if (
            query_lower in title
            or query_lower in description
            or any(query_lower in tag for tag in tags)
        ):
            matches.append(todo)
    return {"count": len(matches), "todos": matches}


def _action_filter_by_tag(params: dict[str, Any]) -> dict[str, Any]:
    tag = params.get("tag", "")
    if not tag or not str(tag).strip():
        raise TodoAgentError("Missing tag parameter")
    tag_lower = str(tag).strip().lower()
    todos = _load_todos()
    matches = [
        t for t in todos
        if tag_lower in [tg.lower() for tg in t.get("tags", [])]
    ]
    return {"count": len(matches), "todos": matches}


def _action_clear_completed(params: dict[str, Any]) -> dict[str, Any]:
    todos = _load_todos()
    before = len(todos)
    todos = [t for t in todos if t.get("status") != "completed"]
    removed = before - len(todos)
    _save_todos(todos)
    return {"removed": removed, "remaining": len(todos)}


def _action_get_stats(params: dict[str, Any]) -> dict[str, Any]:
    todos = _load_todos()
    total = len(todos)
    pending = sum(1 for t in todos if t.get("status") == "pending")
    completed = sum(1 for t in todos if t.get("status") == "completed")
    return {"total": total, "pending": pending, "completed": completed}


def _action_bulk_add(params: dict[str, Any]) -> dict[str, Any]:
    items = params.get("todos")
    if not items or not isinstance(items, list):
        raise TodoAgentError("Missing or invalid todos parameter (expected a list)")

    todos = _load_todos()
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            results.append({"status": "error", "message": "Each todo must be a JSON object"})
            continue
        title = item.get("title", "")
        if not title or not str(title).strip():
            results.append({"status": "error", "message": "Title is required"})
            continue
        todo = _make_todo(
            title=str(title).strip(),
            description=str(item.get("description", "")).strip(),
            tags=item.get("tags"),
            metadata=item.get("metadata"),
        )
        todos.append(todo)
        results.append({"status": "success", "todo": todo})

    _save_todos(todos)
    added = sum(1 for r in results if r["status"] == "success")
    return {"added": added, "total": len(results), "results": results}


def _action_bulk_complete(params: dict[str, Any]) -> dict[str, Any]:
    ids = params.get("ids")
    if not ids or not isinstance(ids, list):
        raise TodoAgentError("Missing or invalid ids parameter (expected a list)")

    todos = _load_todos()
    now = _now_iso()
    results: list[dict[str, Any]] = []
    for todo_id in ids:
        try:
            idx, todo = _find_todo(todos, todo_id)
            if todo["status"] == "completed":
                results.append({"status": "error", "id": todo_id, "message": "Already completed"})
                continue
            todo["status"] = "completed"
            todo["completed_at"] = now
            todo["updated_at"] = now
            todos[idx] = todo
            results.append({"status": "success", "id": todo_id})
        except TodoAgentError as exc:
            results.append({"status": "error", "id": todo_id, "message": str(exc)})

    _save_todos(todos)
    completed = sum(1 for r in results if r["status"] == "success")
    return {"completed": completed, "total": len(results), "results": results}


def _action_bulk_delete(params: dict[str, Any]) -> dict[str, Any]:
    ids = params.get("ids")
    if not ids or not isinstance(ids, list):
        raise TodoAgentError("Missing or invalid ids parameter (expected a list)")

    todos = _load_todos()
    results: list[dict[str, Any]] = []
    ids_to_remove: set[str] = set()
    for todo_id in ids:
        try:
            _find_todo(todos, todo_id)
            ids_to_remove.add(todo_id)
            results.append({"status": "success", "id": todo_id})
        except TodoAgentError as exc:
            results.append({"status": "error", "id": todo_id, "message": str(exc)})

    todos = [t for t in todos if t.get("id") not in ids_to_remove]
    _save_todos(todos)
    deleted = sum(1 for r in results if r["status"] == "success")
    return {"deleted": deleted, "total": len(results), "results": results}


# --------------------------------------------------------------------------- #
# Action registry and parameter validation
# --------------------------------------------------------------------------- #
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "add_todo": ["title"],
    "update_todo": ["id"],
    "complete_todo": ["id"],
    "reopen_todo": ["id"],
    "delete_todo": ["id"],
    "get_todo": ["id"],
    "list_all_todos": [],
    "list_pending_todos": [],
    "list_completed_todos": [],
    "search_todos": ["query"],
    "filter_by_tag": ["tag"],
    "clear_completed": [],
    "get_stats": [],
    "bulk_add": ["todos"],
    "bulk_complete": ["ids"],
    "bulk_delete": ["ids"],
}

_ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "add_todo": _action_add_todo,
    "update_todo": _action_update_todo,
    "complete_todo": _action_complete_todo,
    "reopen_todo": _action_reopen_todo,
    "delete_todo": _action_delete_todo,
    "get_todo": _action_get_todo,
    "list_all_todos": _action_list_all_todos,
    "list_pending_todos": _action_list_pending_todos,
    "list_completed_todos": _action_list_completed_todos,
    "search_todos": _action_search_todos,
    "filter_by_tag": _action_filter_by_tag,
    "clear_completed": _action_clear_completed,
    "get_stats": _action_get_stats,
    "bulk_add": _action_bulk_add,
    "bulk_complete": _action_bulk_complete,
    "bulk_delete": _action_bulk_delete,
}


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def execute(request_json: dict[str, Any]) -> dict[str, Any]:
    """Execute a todo management action.

    Args:
        request_json: A dict with ``"action"`` (str) and ``"parameters"`` (dict).

    Returns:
        A JSON-compatible dict with ``"status"`` (``"success"`` | ``"error"``),
        ``"action"``, and either ``"data"`` or ``"message"``.
    """
    if isinstance(request_json, str):
        request_json = request_json.lstrip("﻿")
        try:
            request_json = json.loads(request_json)
        except json.JSONDecodeError as exc:
            return {"status": "error", "action": "unknown", "message": f"Invalid JSON: {exc}"}

    if not isinstance(request_json, dict):
        return {"status": "error", "action": "unknown", "message": "Request must be a JSON object"}

    action = request_json.get("action", "")
    if not action or not isinstance(action, str):
        return {"status": "error", "action": "unknown", "message": "Missing or invalid action field"}

    if action not in _ACTIONS:
        return {
            "status": "error",
            "action": action,
            "message": f"Unknown action: {action}. Available: {', '.join(sorted(_ACTIONS))}",
        }

    parameters = request_json.get("parameters", {})
    if not isinstance(parameters, dict):
        return {"status": "error", "action": action, "message": "parameters must be a JSON object"}

    required = _REQUIRED_PARAMS.get(action, [])
    for key in required:
        value = parameters.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return {"status": "error", "action": action, "message": f"Missing required parameter: {key}"}

    try:
        data = _ACTIONS[action](parameters)
        return {"status": "success", "action": action, "data": data}
    except TodoAgentError as exc:
        return {"status": "error", "action": action, "message": str(exc)}
    except Exception as exc:
        return {"status": "error", "action": action, "message": f"Unexpected error: {exc}"}


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
def _cli_main() -> None:
    """Handle command-line invocation: file arg, inline JSON arg, or piped stdin."""
    raw: Optional[str] = None

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if os.path.isfile(arg):
            with open(arg, "rb") as fh:
                raw = fh.read().decode("utf-8-sig")
        else:
            raw = arg
    elif not sys.stdin.isatty():
        raw = sys.stdin.buffer.read().decode("utf-8-sig")
    else:
        print(
            "Usage:\n"
            '  python todo_agent.py request.json\n'
            '  python todo_agent.py \'{"action":"add_todo","parameters":{"title":"Buy milk"}}\'\n'
            '  echo \'{"action":"list_all_todos","parameters":{}}\' | python todo_agent.py',
            file=sys.stderr,
        )
        sys.exit(2)

    raw = raw.strip().lstrip("﻿")
    try:
        request_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        result = {"status": "error", "action": "unknown", "message": f"Invalid JSON input: {exc}"}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    result = execute(request_data)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    _cli_main()
