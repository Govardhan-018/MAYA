"""project_tracker_agent.py — Persistent project knowledge-base plugin (TOOL ONLY).

This module is a *pure tool*. It performs **no** business analysis,
recommendations, decision making, prioritization, or project management
advice. It only:

    1. Receives a JSON-compatible ``dict`` request.
    2. Stores / updates / retrieves project data on disk.
    3. Returns a JSON-compatible ``dict`` response.

All intelligence belongs to the calling "Brain Agent". The single public
entry point is :func:`execute`.

Dependencies: Python standard library only.

Storage layout::

    data/projects/index.json          — lightweight project index
    data/projects/{project_id}.json   — full project data per project

CLI usage::

    python project_tracker_agent.py request.json
    python project_tracker_agent.py '{"action":"list_projects","parameters":{}}'
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
    "name": "project_tracker_agent",
    "agent_name": "ProjectTrackerAgent",
    "version": "1.0.0",
    "type": "tool",
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
_BASE_DIR: Path = Path(os.path.dirname(os.path.abspath(__file__)))
_PROJECTS_DIR: Path = _BASE_DIR / "data" / "projects"
_INDEX_FILE: Path = _PROJECTS_DIR / "index.json"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class ProjectTrackerError(Exception):
    """Raised for any handled error whose message is safe to return."""


# --------------------------------------------------------------------------- #
# Timestamp / ID helpers
# --------------------------------------------------------------------------- #
def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Persistence helpers
# --------------------------------------------------------------------------- #
def _ensure_dirs() -> None:
    _PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _project_path(project_id: str) -> Path:
    return _PROJECTS_DIR / f"{project_id}.json"


def _write_json(path: Path, data: Any) -> None:
    _ensure_dirs()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError as exc:
        raise ProjectTrackerError(f"Failed to write {path.name}: {exc}")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ProjectTrackerError(f"Failed to read {path.name}: {exc}")


# --------------------------------------------------------------------------- #
# Index operations
# --------------------------------------------------------------------------- #
def _load_index() -> dict[str, dict[str, str]]:
    data = _read_json(_INDEX_FILE)
    if data is None:
        return {}
    return data


def _save_index(index: dict[str, dict[str, str]]) -> None:
    _write_json(_INDEX_FILE, index)


def _update_index_entry(project: dict[str, Any]) -> None:
    index = _load_index()
    index[project["project_id"]] = {
        "project_name": project["project_name"],
        "status": project["status"],
        "updated_at": project["updated_at"],
    }
    _save_index(index)


def _remove_index_entry(project_id: str) -> None:
    index = _load_index()
    index.pop(project_id, None)
    _save_index(index)


# --------------------------------------------------------------------------- #
# Project load / save
# --------------------------------------------------------------------------- #
def _load_project(project_id: str) -> dict[str, Any]:
    path = _project_path(project_id)
    data = _read_json(path)
    if data is None:
        raise ProjectTrackerError("Project not found")
    return data


def _save_project(project: dict[str, Any]) -> None:
    project["updated_at"] = _now()
    _write_json(_project_path(project["project_id"]), project)
    _update_index_entry(project)


def _log_activity(project: dict[str, Any], action: str, details: str) -> None:
    if "activity_log" not in project:
        project["activity_log"] = []
    project["activity_log"].append({
        "timestamp": _now(),
        "action": action,
        "details": details,
    })


def _new_project(name: str, description: str = "") -> dict[str, Any]:
    now = _now()
    return {
        "project_id": _new_id(),
        "project_name": name,
        "description": description,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "notes": [],
        "todos": [],
        "milestones": [],
        "meetings": [],
        "decisions": [],
        "risks": [],
        "files": [],
        "links": [],
        "progress_updates": [],
        "metadata": {},
        "activity_log": [],
    }


# --------------------------------------------------------------------------- #
# Generic sub-item helpers
# --------------------------------------------------------------------------- #
def _find_item(items: list[dict[str, Any]], item_id: str, label: str) -> tuple[int, dict[str, Any]]:
    for i, item in enumerate(items):
        if item.get("id") == item_id:
            return i, item
    raise ProjectTrackerError(f"{label} not found")


def _resolve_project_id(params: dict[str, Any]) -> str:
    """Get project_id from params, or look it up by project_name."""
    pid = params.get("project_id", "")
    if pid and str(pid).strip():
        return str(pid).strip()

    name = params.get("project_name", "")
    if name and str(name).strip():
        name_lower = str(name).strip().lower()
        index = _load_index()
        for project_id, info in index.items():
            if info.get("project_name", "").lower() == name_lower:
                return project_id
        raise ProjectTrackerError(f"No project found with name: {name}")

    raise ProjectTrackerError("Missing project_id or project_name parameter")


def _require_project_id(params: dict[str, Any]) -> str:
    return _resolve_project_id(params)


def _require_str(params: dict[str, Any], key: str) -> str:
    val = params.get(key, "")
    if not val or not str(val).strip():
        raise ProjectTrackerError(f"Missing {key} parameter")
    return str(val).strip()


# --------------------------------------------------------------------------- #
# Project CRUD actions
# --------------------------------------------------------------------------- #
def _action_create_project(params: dict[str, Any]) -> dict[str, Any]:
    name = _require_str(params, "project_name")
    description = str(params.get("description", "")).strip()
    project = _new_project(name, description)
    if params.get("metadata") and isinstance(params["metadata"], dict):
        project["metadata"] = params["metadata"]
    _log_activity(project, "create_project", f"Project '{name}' created")
    _save_project(project)
    return {"project": project}


def _action_update_project(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    changes: list[str] = []
    for key in ("project_name", "description", "status"):
        if key in params:
            val = str(params[key]).strip()
            if key == "project_name" and not val:
                raise ProjectTrackerError("Project name cannot be empty")
            project[key] = val
            changes.append(key)
    if "metadata" in params and isinstance(params["metadata"], dict):
        project["metadata"].update(params["metadata"])
        changes.append("metadata")
    if not changes:
        raise ProjectTrackerError("No fields to update")
    _log_activity(project, "update_project", f"Updated: {', '.join(changes)}")
    _save_project(project)
    return {"project": project}


def _action_delete_project(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    path = _project_path(pid)
    if not path.exists():
        raise ProjectTrackerError("Project not found")
    try:
        path.unlink()
    except OSError as exc:
        raise ProjectTrackerError(f"Failed to delete project file: {exc}")
    _remove_index_entry(pid)
    return {"deleted": pid}


def _action_get_project(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    return {"project": _load_project(pid)}


def _action_list_projects(params: dict[str, Any]) -> dict[str, Any]:
    index = _load_index()
    projects = [
        {"project_id": pid, **info}
        for pid, info in index.items()
    ]
    return {"count": len(projects), "projects": projects}


def _action_search_projects(params: dict[str, Any]) -> dict[str, Any]:
    query = _require_str(params, "query").lower()
    index = _load_index()
    matches: list[dict[str, Any]] = []

    for pid in index:
        try:
            project = _load_project(pid)
        except ProjectTrackerError:
            continue
        searchable = json.dumps([
            project.get("project_name", ""),
            project.get("description", ""),
            [n.get("title", "") + " " + n.get("content", "") for n in project.get("notes", [])],
            [t.get("title", "") + " " + t.get("description", "") for t in project.get("todos", [])],
            [d.get("title", "") + " " + d.get("rationale", "") for d in project.get("decisions", [])],
            [r.get("title", "") + " " + r.get("description", "") for r in project.get("risks", [])],
            [m.get("title", "") + " " + m.get("agenda", "") for m in project.get("meetings", [])],
            [p.get("content", "") for p in project.get("progress_updates", [])],
        ], ensure_ascii=False).lower()
        if query in searchable:
            matches.append({
                "project_id": pid,
                "project_name": project["project_name"],
                "status": project["status"],
            })
    return {"count": len(matches), "results": matches}


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #
def _action_add_note(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    title = _require_str(params, "title")
    content = str(params.get("content", "")).strip()
    project = _load_project(pid)
    note = {"id": _new_id(), "title": title, "content": content, "created_at": _now(), "updated_at": _now()}
    project["notes"].append(note)
    _log_activity(project, "add_note", f"Note '{title}' added")
    _save_project(project)
    return {"note": note}


def _action_update_note(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    note_id = _require_str(params, "note_id")
    project = _load_project(pid)
    idx, note = _find_item(project["notes"], note_id, "Note")
    for key in ("title", "content"):
        if key in params:
            note[key] = str(params[key]).strip()
    note["updated_at"] = _now()
    project["notes"][idx] = note
    _log_activity(project, "update_note", f"Note '{note['title']}' updated")
    _save_project(project)
    return {"note": note}


def _action_delete_note(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    note_id = _require_str(params, "note_id")
    project = _load_project(pid)
    idx, note = _find_item(project["notes"], note_id, "Note")
    deleted = project["notes"].pop(idx)
    _log_activity(project, "delete_note", f"Note '{deleted['title']}' deleted")
    _save_project(project)
    return {"deleted": deleted}


def _action_list_notes(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    notes = project.get("notes", [])
    return {"count": len(notes), "notes": notes}


# --------------------------------------------------------------------------- #
# Todos
# --------------------------------------------------------------------------- #
def _action_add_todo(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    title = _require_str(params, "title")
    project = _load_project(pid)
    todo = {
        "id": _new_id(),
        "title": title,
        "description": str(params.get("description", "")).strip(),
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": None,
        "tags": params.get("tags", []),
    }
    project["todos"].append(todo)
    _log_activity(project, "add_todo", f"Todo '{title}' added")
    _save_project(project)
    return {"todo": todo}


def _action_update_todo(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    todo_id = _require_str(params, "todo_id")
    project = _load_project(pid)
    idx, todo = _find_item(project["todos"], todo_id, "Todo")
    for key in ("title", "description"):
        if key in params:
            val = str(params[key]).strip()
            if key == "title" and not val:
                raise ProjectTrackerError("Title cannot be empty")
            todo[key] = val
    if "tags" in params:
        todo["tags"] = params["tags"]
    todo["updated_at"] = _now()
    project["todos"][idx] = todo
    _log_activity(project, "update_todo", f"Todo '{todo['title']}' updated")
    _save_project(project)
    return {"todo": todo}


def _action_complete_todo(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    todo_id = _require_str(params, "todo_id")
    project = _load_project(pid)
    idx, todo = _find_item(project["todos"], todo_id, "Todo")
    if todo["status"] == "completed":
        raise ProjectTrackerError("Todo is already completed")
    now = _now()
    todo["status"] = "completed"
    todo["completed_at"] = now
    todo["updated_at"] = now
    project["todos"][idx] = todo
    _log_activity(project, "complete_todo", f"Todo '{todo['title']}' completed")
    _save_project(project)
    return {"todo": todo}


def _action_delete_todo(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    todo_id = _require_str(params, "todo_id")
    project = _load_project(pid)
    idx, todo = _find_item(project["todos"], todo_id, "Todo")
    deleted = project["todos"].pop(idx)
    _log_activity(project, "delete_todo", f"Todo '{deleted['title']}' deleted")
    _save_project(project)
    return {"deleted": deleted}


def _action_list_todos(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    todos = project.get("todos", [])
    return {"count": len(todos), "todos": todos}


# --------------------------------------------------------------------------- #
# Milestones
# --------------------------------------------------------------------------- #
def _action_add_milestone(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    title = _require_str(params, "title")
    project = _load_project(pid)
    milestone = {
        "id": _new_id(),
        "title": title,
        "description": str(params.get("description", "")).strip(),
        "due_date": str(params.get("due_date", "")).strip() or None,
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": None,
    }
    project["milestones"].append(milestone)
    _log_activity(project, "add_milestone", f"Milestone '{title}' added")
    _save_project(project)
    return {"milestone": milestone}


def _action_update_milestone(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    ms_id = _require_str(params, "milestone_id")
    project = _load_project(pid)
    idx, ms = _find_item(project["milestones"], ms_id, "Milestone")
    for key in ("title", "description", "due_date"):
        if key in params:
            ms[key] = str(params[key]).strip() or (None if key == "due_date" else "")
    ms["updated_at"] = _now()
    project["milestones"][idx] = ms
    _log_activity(project, "update_milestone", f"Milestone '{ms['title']}' updated")
    _save_project(project)
    return {"milestone": ms}


def _action_complete_milestone(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    ms_id = _require_str(params, "milestone_id")
    project = _load_project(pid)
    idx, ms = _find_item(project["milestones"], ms_id, "Milestone")
    if ms["status"] == "completed":
        raise ProjectTrackerError("Milestone is already completed")
    now = _now()
    ms["status"] = "completed"
    ms["completed_at"] = now
    ms["updated_at"] = now
    project["milestones"][idx] = ms
    _log_activity(project, "complete_milestone", f"Milestone '{ms['title']}' completed")
    _save_project(project)
    return {"milestone": ms}


def _action_list_milestones(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    milestones = project.get("milestones", [])
    return {"count": len(milestones), "milestones": milestones}


# --------------------------------------------------------------------------- #
# Meetings
# --------------------------------------------------------------------------- #
def _action_add_meeting(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    title = _require_str(params, "title")
    project = _load_project(pid)
    meeting = {
        "id": _new_id(),
        "title": title,
        "date": str(params.get("date", "")).strip() or None,
        "attendees": params.get("attendees", []),
        "agenda": str(params.get("agenda", "")).strip(),
        "notes": str(params.get("notes", "")).strip(),
        "action_items": params.get("action_items", []),
        "created_at": _now(),
        "updated_at": _now(),
    }
    project["meetings"].append(meeting)
    _log_activity(project, "add_meeting", f"Meeting '{title}' added")
    _save_project(project)
    return {"meeting": meeting}


def _action_update_meeting(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    meeting_id = _require_str(params, "meeting_id")
    project = _load_project(pid)
    idx, meeting = _find_item(project["meetings"], meeting_id, "Meeting")
    for key in ("title", "date", "agenda", "notes"):
        if key in params:
            meeting[key] = str(params[key]).strip() or (None if key == "date" else "")
    for key in ("attendees", "action_items"):
        if key in params and isinstance(params[key], list):
            meeting[key] = params[key]
    meeting["updated_at"] = _now()
    project["meetings"][idx] = meeting
    _log_activity(project, "update_meeting", f"Meeting '{meeting['title']}' updated")
    _save_project(project)
    return {"meeting": meeting}


def _action_delete_meeting(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    meeting_id = _require_str(params, "meeting_id")
    project = _load_project(pid)
    idx, meeting = _find_item(project["meetings"], meeting_id, "Meeting")
    deleted = project["meetings"].pop(idx)
    _log_activity(project, "delete_meeting", f"Meeting '{deleted['title']}' deleted")
    _save_project(project)
    return {"deleted": deleted}


def _action_list_meetings(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    meetings = project.get("meetings", [])
    return {"count": len(meetings), "meetings": meetings}


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
def _action_add_decision(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    title = _require_str(params, "title")
    project = _load_project(pid)
    decision = {
        "id": _new_id(),
        "title": title,
        "rationale": str(params.get("rationale", "")).strip(),
        "decided_by": str(params.get("decided_by", "")).strip(),
        "date": str(params.get("date", "")).strip() or _now(),
        "created_at": _now(),
    }
    project["decisions"].append(decision)
    _log_activity(project, "add_decision", f"Decision '{title}' recorded")
    _save_project(project)
    return {"decision": decision}


def _action_list_decisions(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    decisions = project.get("decisions", [])
    return {"count": len(decisions), "decisions": decisions}


# --------------------------------------------------------------------------- #
# Risks
# --------------------------------------------------------------------------- #
def _action_add_risk(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    title = _require_str(params, "title")
    project = _load_project(pid)
    risk = {
        "id": _new_id(),
        "title": title,
        "description": str(params.get("description", "")).strip(),
        "severity": str(params.get("severity", "medium")).strip(),
        "status": "open",
        "mitigation": str(params.get("mitigation", "")).strip(),
        "created_at": _now(),
        "updated_at": _now(),
        "closed_at": None,
    }
    project["risks"].append(risk)
    _log_activity(project, "add_risk", f"Risk '{title}' added")
    _save_project(project)
    return {"risk": risk}


def _action_update_risk(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    risk_id = _require_str(params, "risk_id")
    project = _load_project(pid)
    idx, risk = _find_item(project["risks"], risk_id, "Risk")
    for key in ("title", "description", "severity", "mitigation"):
        if key in params:
            risk[key] = str(params[key]).strip()
    risk["updated_at"] = _now()
    project["risks"][idx] = risk
    _log_activity(project, "update_risk", f"Risk '{risk['title']}' updated")
    _save_project(project)
    return {"risk": risk}


def _action_close_risk(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    risk_id = _require_str(params, "risk_id")
    project = _load_project(pid)
    idx, risk = _find_item(project["risks"], risk_id, "Risk")
    if risk["status"] == "closed":
        raise ProjectTrackerError("Risk is already closed")
    now = _now()
    risk["status"] = "closed"
    risk["closed_at"] = now
    risk["updated_at"] = now
    project["risks"][idx] = risk
    _log_activity(project, "close_risk", f"Risk '{risk['title']}' closed")
    _save_project(project)
    return {"risk": risk}


def _action_list_risks(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    risks = project.get("risks", [])
    return {"count": len(risks), "risks": risks}


# --------------------------------------------------------------------------- #
# Links
# --------------------------------------------------------------------------- #
def _action_add_link(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    url = _require_str(params, "url")
    project = _load_project(pid)
    link = {
        "id": _new_id(),
        "url": url,
        "title": str(params.get("title", "")).strip(),
        "description": str(params.get("description", "")).strip(),
        "created_at": _now(),
    }
    project["links"].append(link)
    _log_activity(project, "add_link", f"Link '{url}' added")
    _save_project(project)
    return {"link": link}


def _action_remove_link(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    link_id = _require_str(params, "link_id")
    project = _load_project(pid)
    idx, link = _find_item(project["links"], link_id, "Link")
    deleted = project["links"].pop(idx)
    _log_activity(project, "remove_link", f"Link '{deleted['url']}' removed")
    _save_project(project)
    return {"deleted": deleted}


def _action_list_links(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    links = project.get("links", [])
    return {"count": len(links), "links": links}


# --------------------------------------------------------------------------- #
# File references
# --------------------------------------------------------------------------- #
def _action_add_file_reference(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    path = _require_str(params, "path")
    project = _load_project(pid)
    ref = {
        "id": _new_id(),
        "path": path,
        "name": str(params.get("name", "")).strip() or os.path.basename(path),
        "description": str(params.get("description", "")).strip(),
        "created_at": _now(),
    }
    project["files"].append(ref)
    _log_activity(project, "add_file_reference", f"File '{ref['name']}' added")
    _save_project(project)
    return {"file": ref}


def _action_remove_file_reference(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    file_id = _require_str(params, "file_id")
    project = _load_project(pid)
    idx, ref = _find_item(project["files"], file_id, "File reference")
    deleted = project["files"].pop(idx)
    _log_activity(project, "remove_file_reference", f"File '{deleted['name']}' removed")
    _save_project(project)
    return {"deleted": deleted}


def _action_list_files(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    files = project.get("files", [])
    return {"count": len(files), "files": files}


# --------------------------------------------------------------------------- #
# Progress updates
# --------------------------------------------------------------------------- #
def _action_add_progress_update(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    content = _require_str(params, "content")
    project = _load_project(pid)
    update = {
        "id": _new_id(),
        "content": content,
        "author": str(params.get("author", "")).strip(),
        "created_at": _now(),
    }
    project["progress_updates"].append(update)
    _log_activity(project, "add_progress_update", "Progress update added")
    _save_project(project)
    return {"progress_update": update}


def _action_list_progress_updates(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    updates = project.get("progress_updates", [])
    return {"count": len(updates), "progress_updates": updates}


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
def _action_get_project_dashboard(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    project = _load_project(pid)
    todos = project.get("todos", [])
    milestones = project.get("milestones", [])
    risks = project.get("risks", [])
    return {
        "project_name": project["project_name"],
        "status": project["status"],
        "total_todos": len(todos),
        "completed_todos": sum(1 for t in todos if t.get("status") == "completed"),
        "total_milestones": len(milestones),
        "completed_milestones": sum(1 for m in milestones if m.get("status") == "completed"),
        "total_risks": len(risks),
        "open_risks": sum(1 for r in risks if r.get("status") == "open"),
        "total_notes": len(project.get("notes", [])),
        "total_meetings": len(project.get("meetings", [])),
        "total_decisions": len(project.get("decisions", [])),
        "total_links": len(project.get("links", [])),
        "total_files": len(project.get("files", [])),
        "total_progress_updates": len(project.get("progress_updates", [])),
        "last_update": project.get("updated_at", ""),
    }


# --------------------------------------------------------------------------- #
# Bulk operations
# --------------------------------------------------------------------------- #
def _action_bulk_add_todos(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    items = params.get("todos")
    if not items or not isinstance(items, list):
        raise ProjectTrackerError("Missing or invalid todos parameter (expected a list)")
    project = _load_project(pid)
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            results.append({"status": "error", "message": "Each todo must be a JSON object"})
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            results.append({"status": "error", "message": "Title is required"})
            continue
        todo = {
            "id": _new_id(),
            "title": title,
            "description": str(item.get("description", "")).strip(),
            "status": "pending",
            "created_at": _now(),
            "updated_at": _now(),
            "completed_at": None,
            "tags": item.get("tags", []),
        }
        project["todos"].append(todo)
        results.append({"status": "success", "todo": todo})
    added = sum(1 for r in results if r["status"] == "success")
    _log_activity(project, "bulk_add_todos", f"{added} todos added")
    _save_project(project)
    return {"added": added, "total": len(results), "results": results}


def _action_bulk_complete_todos(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    ids = params.get("todo_ids")
    if not ids or not isinstance(ids, list):
        raise ProjectTrackerError("Missing or invalid todo_ids parameter (expected a list)")
    project = _load_project(pid)
    now = _now()
    results: list[dict[str, Any]] = []
    for todo_id in ids:
        try:
            idx, todo = _find_item(project["todos"], todo_id, "Todo")
            if todo["status"] == "completed":
                results.append({"status": "error", "id": todo_id, "message": "Already completed"})
                continue
            todo["status"] = "completed"
            todo["completed_at"] = now
            todo["updated_at"] = now
            project["todos"][idx] = todo
            results.append({"status": "success", "id": todo_id})
        except ProjectTrackerError as exc:
            results.append({"status": "error", "id": todo_id, "message": str(exc)})
    completed = sum(1 for r in results if r["status"] == "success")
    _log_activity(project, "bulk_complete_todos", f"{completed} todos completed")
    _save_project(project)
    return {"completed": completed, "total": len(results), "results": results}


def _action_bulk_add_notes(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    items = params.get("notes")
    if not items or not isinstance(items, list):
        raise ProjectTrackerError("Missing or invalid notes parameter (expected a list)")
    project = _load_project(pid)
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            results.append({"status": "error", "message": "Each note must be a JSON object"})
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            results.append({"status": "error", "message": "Title is required"})
            continue
        note = {
            "id": _new_id(),
            "title": title,
            "content": str(item.get("content", "")).strip(),
            "created_at": _now(),
            "updated_at": _now(),
        }
        project["notes"].append(note)
        results.append({"status": "success", "note": note})
    added = sum(1 for r in results if r["status"] == "success")
    _log_activity(project, "bulk_add_notes", f"{added} notes added")
    _save_project(project)
    return {"added": added, "total": len(results), "results": results}


def _action_bulk_add_files(params: dict[str, Any]) -> dict[str, Any]:
    pid = _require_project_id(params)
    items = params.get("files")
    if not items or not isinstance(items, list):
        raise ProjectTrackerError("Missing or invalid files parameter (expected a list)")
    project = _load_project(pid)
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            results.append({"status": "error", "message": "Each file must be a JSON object"})
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            results.append({"status": "error", "message": "Path is required"})
            continue
        ref = {
            "id": _new_id(),
            "path": path,
            "name": str(item.get("name", "")).strip() or os.path.basename(path),
            "description": str(item.get("description", "")).strip(),
            "created_at": _now(),
        }
        project["files"].append(ref)
        results.append({"status": "success", "file": ref})
    added = sum(1 for r in results if r["status"] == "success")
    _log_activity(project, "bulk_add_files", f"{added} file references added")
    _save_project(project)
    return {"added": added, "total": len(results), "results": results}


# --------------------------------------------------------------------------- #
# Action registry and parameter validation
# --------------------------------------------------------------------------- #
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "create_project": ["project_name"],
    "update_project": ["project_id"],
    "delete_project": ["project_id"],
    "get_project": ["project_id"],
    "list_projects": [],
    "search_projects": ["query"],
    "add_note": ["project_id", "title"],
    "update_note": ["project_id", "note_id"],
    "delete_note": ["project_id", "note_id"],
    "list_notes": ["project_id"],
    "add_todo": ["project_id", "title"],
    "update_todo": ["project_id", "todo_id"],
    "complete_todo": ["project_id", "todo_id"],
    "delete_todo": ["project_id", "todo_id"],
    "list_todos": ["project_id"],
    "add_milestone": ["project_id", "title"],
    "update_milestone": ["project_id", "milestone_id"],
    "complete_milestone": ["project_id", "milestone_id"],
    "list_milestones": ["project_id"],
    "add_meeting": ["project_id", "title"],
    "update_meeting": ["project_id", "meeting_id"],
    "delete_meeting": ["project_id", "meeting_id"],
    "list_meetings": ["project_id"],
    "add_decision": ["project_id", "title"],
    "list_decisions": ["project_id"],
    "add_risk": ["project_id", "title"],
    "update_risk": ["project_id", "risk_id"],
    "close_risk": ["project_id", "risk_id"],
    "list_risks": ["project_id"],
    "add_link": ["project_id", "url"],
    "remove_link": ["project_id", "link_id"],
    "list_links": ["project_id"],
    "add_file_reference": ["project_id", "path"],
    "remove_file_reference": ["project_id", "file_id"],
    "list_files": ["project_id"],
    "add_progress_update": ["project_id", "content"],
    "list_progress_updates": ["project_id"],
    "get_project_dashboard": ["project_id"],
    "bulk_add_todos": ["project_id", "todos"],
    "bulk_complete_todos": ["project_id", "todo_ids"],
    "bulk_add_notes": ["project_id", "notes"],
    "bulk_add_files": ["project_id", "files"],
}

_ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "create_project": _action_create_project,
    "update_project": _action_update_project,
    "delete_project": _action_delete_project,
    "get_project": _action_get_project,
    "list_projects": _action_list_projects,
    "search_projects": _action_search_projects,
    "add_note": _action_add_note,
    "update_note": _action_update_note,
    "delete_note": _action_delete_note,
    "list_notes": _action_list_notes,
    "add_todo": _action_add_todo,
    "update_todo": _action_update_todo,
    "complete_todo": _action_complete_todo,
    "delete_todo": _action_delete_todo,
    "list_todos": _action_list_todos,
    "add_milestone": _action_add_milestone,
    "update_milestone": _action_update_milestone,
    "complete_milestone": _action_complete_milestone,
    "list_milestones": _action_list_milestones,
    "add_meeting": _action_add_meeting,
    "update_meeting": _action_update_meeting,
    "delete_meeting": _action_delete_meeting,
    "list_meetings": _action_list_meetings,
    "add_decision": _action_add_decision,
    "list_decisions": _action_list_decisions,
    "add_risk": _action_add_risk,
    "update_risk": _action_update_risk,
    "close_risk": _action_close_risk,
    "list_risks": _action_list_risks,
    "add_link": _action_add_link,
    "remove_link": _action_remove_link,
    "list_links": _action_list_links,
    "add_file_reference": _action_add_file_reference,
    "remove_file_reference": _action_remove_file_reference,
    "list_files": _action_list_files,
    "add_progress_update": _action_add_progress_update,
    "list_progress_updates": _action_list_progress_updates,
    "get_project_dashboard": _action_get_project_dashboard,
    "bulk_add_todos": _action_bulk_add_todos,
    "bulk_complete_todos": _action_bulk_complete_todos,
    "bulk_add_notes": _action_bulk_add_notes,
    "bulk_add_files": _action_bulk_add_files,
}


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def execute(request_json: dict[str, Any]) -> dict[str, Any]:
    """Execute a project tracker action.

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
    except ProjectTrackerError as exc:
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
            '  python project_tracker_agent.py request.json\n'
            '  python project_tracker_agent.py \'{"action":"list_projects","parameters":{}}\'\n'
            '  echo \'{"action":"list_projects","parameters":{}}\' '
            "| python project_tracker_agent.py",
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
