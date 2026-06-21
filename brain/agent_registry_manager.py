"""Reads and indexes the Phase 0 registry files.

Provides fast lookups: agent exists? action exists? what params are required?
All data comes from system/*.json — nothing is hardcoded.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from brain.utils.config import (
    ACTION_REGISTRY_PATH,
    AGENT_REGISTRY_PATH,
    CAPABILITIES_PATH,
    PLANNER_CONTEXT_PATH,
)
from brain.utils.logger import log_brain


class AgentRegistryManager:
    """In-memory index over the Phase 0 registry files."""

    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        self._actions: dict[str, dict[str, Any]] = {}
        self._agent_actions: dict[str, set[str]] = {}
        self._required_params: dict[str, dict[str, list[str]]] = {}
        self._planner_context: dict[str, Any] = {}
        self._capabilities: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Load all registry files into memory."""
        self._load_agent_registry()
        self._load_action_registry()
        self._load_planner_context()
        self._load_capabilities()
        self._loaded = True
        log_brain(
            "registry_loaded",
            agent_count=len(self._agents),
            action_count=len(self._actions),
        )

    def _load_agent_registry(self) -> None:
        raw = json.loads(AGENT_REGISTRY_PATH.read_text(encoding="utf-8"))
        for agent in raw.get("agents", []):
            name = agent["name"]
            self._agents[name] = agent
            action_names: set[str] = set()
            params_map: dict[str, list[str]] = {}
            for action in agent.get("actions", []):
                action_names.add(action["name"])
                params_map[action["name"]] = action.get("required_params", [])
            self._agent_actions[name] = action_names
            self._required_params[name] = params_map

    def _load_action_registry(self) -> None:
        raw = json.loads(ACTION_REGISTRY_PATH.read_text(encoding="utf-8"))
        for action in raw.get("actions", []):
            key = f"{action['agent']}.{action['action']}"
            self._actions[key] = action

    def _load_planner_context(self) -> None:
        self._planner_context = json.loads(
            PLANNER_CONTEXT_PATH.read_text(encoding="utf-8")
        )

    def _load_capabilities(self) -> None:
        self._capabilities = json.loads(
            CAPABILITIES_PATH.read_text(encoding="utf-8")
        )

    def reload(self) -> None:
        """Re-read all registry files (call after build_registry.py runs)."""
        self._agents.clear()
        self._actions.clear()
        self._agent_actions.clear()
        self._required_params.clear()
        self.load()

    # ── queries ────────────────────────────────────────────────────────────

    def agent_exists(self, agent_name: str) -> bool:
        return agent_name in self._agents

    def action_exists(self, agent_name: str, action_name: str) -> bool:
        return action_name in self._agent_actions.get(agent_name, set())

    def get_required_params(self, agent_name: str, action_name: str) -> list[str]:
        return self._required_params.get(agent_name, {}).get(action_name, [])

    def get_agent_info(self, agent_name: str) -> Optional[dict[str, Any]]:
        return self._agents.get(agent_name)

    def get_agent_file(self, agent_name: str) -> Optional[str]:
        info = self._agents.get(agent_name)
        return info["file"] if info else None

    def get_agent_entrypoint(self, agent_name: str) -> str:
        info = self._agents.get(agent_name)
        return info.get("entrypoint", "execute") if info else "execute"

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    def list_actions(self, agent_name: str) -> list[str]:
        return sorted(self._agent_actions.get(agent_name, set()))

    def get_planner_context(self) -> dict[str, Any]:
        return self._planner_context

    def get_planner_context_compact(self) -> str:
        """Return a compact JSON string for embedding in the planner prompt."""
        agents = self._planner_context.get("agents", [])
        compact: list[dict[str, Any]] = []
        for agent in agents:
            entry: dict[str, Any] = {
                "agent": agent["agent"],
                "purpose": agent.get("purpose", ""),
                "keywords": agent.get("keywords", []),
                "actions": [],
            }
            for action in agent.get("actions", []):
                a: dict[str, Any] = {"name": action["name"]}
                if action.get("required_params"):
                    a["required_params"] = action["required_params"]
                if action.get("optional_params"):
                    a["optional_params"] = action["optional_params"]
                entry["actions"].append(a)
            compact.append(entry)
        return json.dumps(compact, ensure_ascii=False)

    def validate_task(
        self, agent_name: str, action_name: str, parameters: dict[str, Any]
    ) -> list[str]:
        """Return a list of validation errors (empty = valid)."""
        errors: list[str] = []

        if not self.agent_exists(agent_name):
            errors.append(f"Unknown agent: {agent_name}")
            return errors

        if not self.action_exists(agent_name, action_name):
            errors.append(
                f"Unknown action '{action_name}' for agent '{agent_name}'"
            )
            return errors

        required = self.get_required_params(agent_name, action_name)
        for param in required:
            if param not in parameters:
                errors.append(
                    f"Missing required parameter '{param}' for "
                    f"{agent_name}.{action_name}"
                )

        return errors
