"""memory_agent.py — Memory management plugin for the MAYA Brain.

This agent exposes memory operations (store, retrieve, search, archive,
summarize, update, delete) via the standard PLUGIN_INFO / execute interface.

Dependencies: memory/ package.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

__all__ = ["execute", "PLUGIN_INFO"]

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── plugin metadata ──────────────────────────────────────────────────────

PLUGIN_INFO: dict[str, str] = {
    "name": "memory_agent",
    "agent_name": "MemoryAgent",
    "version": "1.0.0",
    "type": "tool",
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
    "description": "Long-term memory management — store, search, and retrieve memories",
}

# ── lazy memory manager singleton ─────────────────────────────────────────

_manager = None


def _get_manager():
    global _manager
    if _manager is None:
        from memory.memory_manager import MemoryManager
        _manager = MemoryManager()
        _manager.startup()
    return _manager


# ── action handlers ───────────────────────────────────────────────────────

def _store_memory(params: dict[str, Any]) -> dict[str, Any]:
    mgr = _get_manager()
    mid = mgr.store_memory(
        category=params["category"],
        content=params["content"],
        importance=params.get("importance", 0.8),
        tags=params.get("tags", []),
    )
    if mid:
        return {"status": "success", "message": "Memory stored", "memory_id": mid}
    return {"status": "success", "message": "Memory not stored (below threshold or duplicate)"}


def _retrieve_memory(params: dict[str, Any]) -> dict[str, Any]:
    mgr = _get_manager()
    memory_id = params.get("memory_id")
    if memory_id:
        mem = mgr.long_term.get_memory_by_id(memory_id)
        if mem:
            return {"status": "success", "memory": mem.model_dump(mode="json")}
        return {"status": "error", "message": f"Memory '{memory_id}' not found"}

    category = params.get("category")
    memories = mgr.long_term.get_memories(category)
    return {
        "status": "success",
        "count": len(memories),
        "memories": [m.model_dump(mode="json") for m in memories[:20]],
    }


def _search_memory(params: dict[str, Any]) -> dict[str, Any]:
    mgr = _get_manager()
    query = params["query"]
    category = params.get("category")
    limit = params.get("limit", 10)

    keyword_results = mgr.search_memory(query, category=category, limit=limit)

    try:
        vector_results = mgr.search_vector(query, top_k=limit)
    except Exception:
        vector_results = []

    return {
        "status": "success",
        "keyword_results": [m.model_dump(mode="json") for m in keyword_results],
        "vector_results": vector_results,
    }


def _archive_chat(params: dict[str, Any]) -> dict[str, Any]:
    mgr = _get_manager()
    summary, new_id = mgr.force_rotate()
    result: dict[str, Any] = {
        "status": "success",
        "new_chat_id": new_id,
        "message": "Chat archived and new chat started",
    }
    if summary:
        result["summary"] = summary.summary
    return result


def _create_summary(params: dict[str, Any]) -> dict[str, Any]:
    mgr = _get_manager()
    summary = mgr.create_summary_of_current()
    if summary:
        return {
            "status": "success",
            "summary": summary.model_dump(mode="json"),
        }
    return {"status": "success", "message": "No messages to summarize"}


def _update_memory(params: dict[str, Any]) -> dict[str, Any]:
    mgr = _get_manager()
    success = mgr.update_memory(
        memory_id=params["memory_id"],
        content=params.get("content"),
        importance=params.get("importance"),
        tags=params.get("tags"),
    )
    if success:
        return {"status": "success", "message": "Memory updated"}
    return {"status": "error", "message": "Memory not found"}


def _delete_memory(params: dict[str, Any]) -> dict[str, Any]:
    mgr = _get_manager()
    success = mgr.delete_memory(params["memory_id"])
    if success:
        return {"status": "success", "message": "Memory deleted"}
    return {"status": "error", "message": "Memory not found"}


def _get_status(params: dict[str, Any]) -> dict[str, Any]:
    mgr = _get_manager()
    return {"status": "success", "memory_status": mgr.get_status()}


# ── action registry ──────────────────────────────────────────────────────

_ACTIONS: dict[str, Callable] = {
    "store_memory": _store_memory,
    "retrieve_memory": _retrieve_memory,
    "search_memory": _search_memory,
    "archive_chat": _archive_chat,
    "create_summary": _create_summary,
    "update_memory": _update_memory,
    "delete_memory": _delete_memory,
    "get_status": _get_status,
}

_REQUIRED_PARAMS: dict[str, list[str]] = {
    "store_memory": ["category", "content"],
    "retrieve_memory": [],
    "search_memory": ["query"],
    "archive_chat": [],
    "create_summary": [],
    "update_memory": ["memory_id"],
    "delete_memory": ["memory_id"],
    "get_status": [],
}

# ── public entry point ────────────────────────────────────────────────────


def execute(request_json: dict[str, Any]) -> dict[str, Any]:
    """Standard MAYA agent entry point."""
    action = request_json.get("action", "")
    params = request_json.get("parameters", {})

    handler = _ACTIONS.get(action)
    if handler is None:
        return {
            "status": "error",
            "message": f"Unknown action: {action}",
            "available_actions": list(_ACTIONS.keys()),
        }

    required = _REQUIRED_PARAMS.get(action, [])
    missing = [p for p in required if p not in params]
    if missing:
        return {
            "status": "error",
            "message": f"Missing required parameters: {missing}",
        }

    try:
        return handler(params)
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }


# ── CLI shim ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python memory_agent.py '<json_request>'")
        sys.exit(1)
    arg = sys.argv[1]
    if Path(arg).exists():
        request = json.loads(Path(arg).read_text(encoding="utf-8"))
    else:
        request = json.loads(arg)
    result = execute(request)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
