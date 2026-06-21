"""_template_agent.py — Template for creating new MAYA plugins.

Copy this file, rename it to <your_agent>_agent.py, and fill in the sections.
Then run: python build_registry.py
The new agent will be auto-discovered by the Brain and appear in the HUD.

Entry point contract:
    - execute(request: dict) -> dict
    - request has {"action": "<action_name>", "parameters": {...}}
    - response has {"status": "success"|"error", ...}
"""

from __future__ import annotations

from typing import Any

__all__ = ["execute", "PLUGIN_INFO"]


# ── Plugin metadata (required) ──────────────────────────────────────────────
# The build_registry.py scanner reads this to register the agent.
# Include keywords/use_cases here so you never need to edit build_registry.py.
PLUGIN_INFO: dict[str, Any] = {
    # Required fields
    "name": "template_agent",           # unique snake_case id
    "agent_name": "TemplateAgent",      # display class name
    "version": "1.0.0",
    "type": "tool",                     # "tool" | "service" | "integration"
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
    "description": "One-line description of what this agent does",

    # Self-describing metadata (optional but recommended)
    # If present, build_registry.py uses these instead of its hardcoded dicts.
    "keywords": [
        "keyword1", "keyword2", "keyword3",
    ],
    "suggested_use_cases": [
        "Do something useful",
        "Handle a specific task",
    ],
    "avoid_use_cases": [
        "Things this agent should NOT be used for",
    ],
    # Optional params per action (mirrors _OPTIONAL_PARAMS in build_registry)
    "optional_params": {
        "sample_action": ["optional_field_1"],
    },
    # Example I/O per action (mirrors _EXAMPLES in build_registry)
    "examples": {
        "sample_action": {
            "input": {"action": "sample_action", "parameters": {"query": "hello"}},
            "output_summary": "Returns a greeting message",
        },
    },
}


# ── Action registry ─────────────────────────────────────────────────────────
# Map action names to handler functions. build_registry.py reads _ACTIONS.
_ACTIONS: dict[str, Any] = {}

# Map action names to their required parameter names.
_REQUIRED_PARAMS: dict[str, list[str]] = {}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sample_action(params: dict[str, Any]) -> dict[str, Any]:
    """Perform a sample action with the given query."""
    query = params.get("query", "")
    return {
        "status": "success",
        "message": f"Template processed: {query}",
        "data": {},
    }


# Register actions
_ACTIONS["sample_action"] = _sample_action
_REQUIRED_PARAMS["sample_action"] = ["query"]


# ── Entry point ──────────────────────────────────────────────────────────────

def execute(request: dict[str, Any]) -> dict[str, Any]:
    """Route the request to the correct action handler."""
    action = request.get("action", "")
    params = request.get("parameters", {})

    handler = _ACTIONS.get(action)
    if handler is None:
        return {
            "status": "error",
            "message": f"Unknown action: {action}",
            "available_actions": list(_ACTIONS.keys()),
        }

    return handler(params)
