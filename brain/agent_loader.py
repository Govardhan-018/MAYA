"""Dynamic agent loader — imports agent modules from agents/ at runtime.

Agents are loaded on first use and cached. The loader reads file paths from
the agent registry (Phase 0) so no agent names are hardcoded.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional

from brain.agent_registry_manager import AgentRegistryManager
from brain.utils.config import AGENTS_DIR
from brain.utils.logger import log_brain


class AgentLoader:
    """Thread-safe, lazy-loading agent module cache."""

    def __init__(self, registry: AgentRegistryManager) -> None:
        self._registry = registry
        self._cache: dict[str, ModuleType] = {}
        self._lock = threading.Lock()

    def _import_module(self, agent_name: str) -> ModuleType:
        """Import an agent .py file by name, using the registry for the filename."""
        filename = self._registry.get_agent_file(agent_name)
        if filename is None:
            raise ImportError(f"Agent '{agent_name}' not found in registry")

        module_path = AGENTS_DIR / filename
        if not module_path.is_file():
            raise ImportError(f"Agent file not found: {module_path}")

        spec = importlib.util.spec_from_file_location(agent_name, str(module_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create import spec for {module_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[agent_name] = module
        spec.loader.exec_module(module)
        return module

    def get_module(self, agent_name: str) -> ModuleType:
        """Return the cached module for *agent_name*, importing on first call."""
        if agent_name in self._cache:
            return self._cache[agent_name]

        with self._lock:
            if agent_name in self._cache:
                return self._cache[agent_name]

            module = self._import_module(agent_name)
            self._cache[agent_name] = module
            log_brain("agent_loaded", agent=agent_name)
            return module

    def get_execute_fn(self, agent_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        """Return the execute() callable for *agent_name*."""
        module = self.get_module(agent_name)
        entrypoint = self._registry.get_agent_entrypoint(agent_name)
        fn = getattr(module, entrypoint, None)
        if fn is None or not callable(fn):
            raise AttributeError(
                f"Agent '{agent_name}' has no callable '{entrypoint}'"
            )
        return fn

    def preload_all(self) -> dict[str, Optional[str]]:
        """Import every registered agent up front. Returns {name: error|None}."""
        results: dict[str, Optional[str]] = {}
        for agent_name in self._registry.list_agents():
            try:
                self.get_module(agent_name)
                results[agent_name] = None
            except Exception as exc:
                results[agent_name] = str(exc)
                log_brain("agent_load_failed", agent=agent_name, error=str(exc))
        return results

    def is_loaded(self, agent_name: str) -> bool:
        return agent_name in self._cache

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
