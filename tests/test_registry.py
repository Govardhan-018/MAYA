"""test_registry.py — Validate the generated registry files.

Run after build_registry.py:

    python -m pytest tests/test_registry.py -v

Or standalone:

    python tests/test_registry.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_DIR = PROJECT_ROOT / "system"
AGENTS_DIR = PROJECT_ROOT / "agents"
DOCS_DIR = SYSTEM_DIR / "generated_docs"


def _load(name: str) -> dict:
    path = SYSTEM_DIR / name
    assert path.exists(), f"Missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _agent_files() -> list[str]:
    return [
        f.stem for f in sorted(AGENTS_DIR.glob("*.py"))
        if not f.name.startswith("_")
    ]


# ── structural tests ──────────────────────────────────────────────────────
def test_agent_registry_structure():
    data = _load("agent_registry.json")
    assert "version" in data
    assert "generated_at" in data
    assert "agent_count" in data
    assert isinstance(data["agents"], list)
    assert data["agent_count"] == len(data["agents"])
    assert data["agent_count"] > 0


def test_action_registry_structure():
    data = _load("action_registry.json")
    assert "total_actions" in data
    assert isinstance(data["actions"], list)
    assert data["total_actions"] == len(data["actions"])
    assert data["total_actions"] > 0


def test_capabilities_structure():
    data = _load("agent_capabilities.json")
    assert "capabilities" in data
    assert isinstance(data["capabilities"], list)
    assert data["agent_count"] == len(data["capabilities"])


def test_planner_context_structure():
    data = _load("planner_context.json")
    assert "instruction" in data
    assert isinstance(data["agents"], list)
    assert len(data["agents"]) > 0


# ── completeness tests ────────────────────────────────────────────────────
def test_all_agents_registered():
    """Every .py file in agents/ should appear in the registry."""
    data = _load("agent_registry.json")
    registered = {a["name"] for a in data["agents"]}
    on_disk = set(_agent_files())
    missing = on_disk - registered
    assert not missing, f"Agents on disk but not in registry: {missing}"


def test_all_agents_have_docs():
    """Every registered agent should have a generated doc file."""
    data = _load("agent_registry.json")
    for agent in data["agents"]:
        doc_path = DOCS_DIR / f"{agent['name']}.md"
        assert doc_path.exists(), f"Missing doc: {doc_path}"
        content = doc_path.read_text(encoding="utf-8")
        assert len(content) > 100, f"Doc too short: {doc_path}"


def test_all_actions_in_action_registry():
    """Every action from agent_registry should appear in action_registry."""
    agents = _load("agent_registry.json")
    actions = _load("action_registry.json")
    action_set = {(a["agent"], a["action"]) for a in actions["actions"]}

    for agent in agents["agents"]:
        for action in agent["actions"]:
            pair = (agent["name"], action["name"])
            assert pair in action_set, f"Missing from action_registry: {pair}"


def test_planner_context_covers_all_agents():
    """planner_context.json should cover every registered agent."""
    agents = _load("agent_registry.json")
    planner = _load("planner_context.json")
    planner_agents = {a["agent"] for a in planner["agents"]}
    registered = {a["name"] for a in agents["agents"]}
    assert planner_agents == registered


# ── data quality tests ─────────────────────────────────────────────────────
def test_every_agent_has_keywords():
    data = _load("agent_capabilities.json")
    for cap in data["capabilities"]:
        assert len(cap["keywords"]) > 0, f"{cap['agent']} has no keywords"


def test_every_agent_has_actions():
    data = _load("agent_registry.json")
    for agent in data["agents"]:
        assert agent["action_count"] > 0, f"{agent['name']} has no actions"


def test_required_params_are_lists():
    data = _load("action_registry.json")
    for action in data["actions"]:
        assert isinstance(action["required_params"], list), (
            f"{action['agent']}.{action['action']}: required_params is not a list"
        )


def test_no_duplicate_actions_per_agent():
    data = _load("agent_registry.json")
    for agent in data["agents"]:
        names = [a["name"] for a in agent["actions"]]
        assert len(names) == len(set(names)), (
            f"{agent['name']} has duplicate actions"
        )


def test_planner_context_has_instruction():
    data = _load("planner_context.json")
    assert len(data["instruction"]) > 20


def test_action_registry_no_orphans():
    """Every agent referenced in action_registry should exist in agent_registry."""
    agents = _load("agent_registry.json")
    actions = _load("action_registry.json")
    registered = {a["name"] for a in agents["agents"]}
    for action in actions["actions"]:
        assert action["agent"] in registered, (
            f"action_registry references unknown agent: {action['agent']}"
        )


# ── runner ─────────────────────────────────────────────────────────────────
def _run_all() -> int:
    """Run all test_* functions and report results."""
    tests = [
        (name, func)
        for name, func in sorted(globals().items())
        if name.startswith("test_") and callable(func)
    ]

    passed = 0
    failed = 0

    for name, func in tests:
        try:
            func()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERROR {name}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run_all())
