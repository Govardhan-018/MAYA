"""maya_code_agent.py — Autonomous coding agent plugin.

Text-only, background-threaded coding agent that analyzes a project,
generates a plan via LLM, executes it with safety validation and
rollback capability, and reports live status for UI polling.

This file is the registry entry point.  All logic lives in the
``agents.maya_code`` package.
"""

from __future__ import annotations

import json
import sys
from typing import Any

__all__ = ["execute", "PLUGIN_INFO"]

# ── plugin metadata (self-describing for build_registry.py) ──────────────────

PLUGIN_INFO: dict[str, Any] = {
    "name": "maya_code_agent",
    "agent_name": "MayaCodeAgent",
    "version": "1.0.0",
    "type": "tool",
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
    "description": "Autonomous coding agent — plans, writes, tests, and fixes code in a target project",
    "voice_enabled": False,
    "keywords": [
        "code", "coding", "develop", "build", "create", "fix", "debug",
        "refactor", "write code", "implement", "program", "script",
    ],
    "suggested_use_cases": [
        "Build a feature end-to-end in a target project",
        "Fix a bug from an error traceback",
        "Add tests to an existing codebase",
        "Refactor code following a specific pattern",
    ],
    "avoid_use_cases": [
        "Quick questions that don't need code changes",
        "File browsing (use file_agent instead)",
        "Web searches or API calls",
    ],
}

# ── actions ──────────────────────────────────────────────────────────────────

_ACTIONS: dict[str, str] = {
    "start_task":   "Start a coding task in the background",
    "get_status":   "Poll the status of a running task",
    "cancel_task":  "Cancel a running task",
    "list_jobs":    "List all coding jobs",
}

_REQUIRED_PARAMS: dict[str, list[str]] = {
    "start_task":  ["goal", "project_root"],
    "get_status":  ["job_id"],
    "cancel_task": ["job_id"],
    "list_jobs":   [],
}


# ── entry point ──────────────────────────────────────────────────────────────

def execute(request: dict) -> dict:
    """Dispatch to the appropriate action handler.

    Expected request shape::

        {
            "action": "start_task",
            "parameters": {
                "goal": "Add user authentication to the Flask app",
                "project_root": "/home/user/myproject",
                "dry_run": false,
                "context": "optional extra context"
            }
        }
    """
    try:
        action = request.get("action", "").strip()
        params = request.get("parameters", {})

        if not action:
            return _error("Missing 'action' field")

        if action not in _ACTIONS:
            return _error(f"Unknown action: {action!r}. Available: {', '.join(_ACTIONS)}")

        required = _REQUIRED_PARAMS.get(action, [])
        missing = [p for p in required if not params.get(p)]
        if missing:
            return _error(f"Missing required parameters for '{action}': {', '.join(missing)}")

        # lazy import to avoid loading heavy deps when brain just scans PLUGIN_INFO
        from agents.maya_code.runner import start_task, get_status, cancel_task, list_jobs

        if action == "start_task":
            return start_task(
                goal=params["goal"],
                project_root=params["project_root"],
                dry_run=params.get("dry_run", False),
                context=params.get("context"),
            )
        elif action == "get_status":
            return get_status(job_id=params["job_id"])
        elif action == "cancel_task":
            return cancel_task(job_id=params["job_id"])
        elif action == "list_jobs":
            return list_jobs()

        return _error(f"Unhandled action: {action}")

    except Exception as exc:
        return _error(f"Agent error: {type(exc).__name__}: {exc}")


def _error(message: str) -> dict:
    return {"status": "error", "message": message}


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python maya_code_agent.py '<json_request>'")
        sys.exit(1)

    try:
        req = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {exc}"}))
        sys.exit(1)

    result = execute(req)
    print(json.dumps(result, indent=2))
