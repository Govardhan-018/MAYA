"""Tests for the Brain Core — registry, schemas, queue, loader, executor.

These tests run without Ollama (LLM calls are mocked or skipped).
Run:
    python -m pytest tests/test_brain.py -v
    python tests/test_brain.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from brain.agent_registry_manager import AgentRegistryManager
from brain.agent_loader import AgentLoader
from brain.queue_manager import WorkQueue
from brain.executor import AgentExecutor
from brain.schemas.plan_schema import (
    ExecutionPlan,
    PlanTask,
    TaskResult,
    TaskStatus,
)


# ═══════════════════════════════════════════════════════════════════════════
# Registry Manager Tests
# ═══════════════════════════════════════════════════════════════════════════

def _make_registry() -> AgentRegistryManager:
    r = AgentRegistryManager()
    r.load()
    return r


def test_registry_loads():
    r = _make_registry()
    agents = r.list_agents()
    assert len(agents) >= 9
    assert "gmail_agent" in agents
    assert "weather_agent" in agents


def test_registry_agent_exists():
    r = _make_registry()
    assert r.agent_exists("gmail_agent")
    assert not r.agent_exists("nonexistent_agent")


def test_registry_action_exists():
    r = _make_registry()
    assert r.action_exists("gmail_agent", "get_latest_emails")
    assert r.action_exists("weather_agent", "current_weather")
    assert not r.action_exists("gmail_agent", "fake_action")


def test_registry_required_params():
    r = _make_registry()
    params = r.get_required_params("gmail_agent", "search_sender")
    assert "sender" in params


def test_registry_validate_task_valid():
    r = _make_registry()
    errors = r.validate_task("gmail_agent", "search_sender", {"sender": "test@x.com"})
    assert errors == []


def test_registry_validate_task_missing_param():
    r = _make_registry()
    errors = r.validate_task("gmail_agent", "search_sender", {})
    assert any("sender" in e for e in errors)


def test_registry_validate_task_bad_agent():
    r = _make_registry()
    errors = r.validate_task("fake_agent", "do_stuff", {})
    assert any("Unknown agent" in e for e in errors)


def test_registry_validate_task_bad_action():
    r = _make_registry()
    errors = r.validate_task("gmail_agent", "nope", {})
    assert any("Unknown action" in e for e in errors)


def test_registry_planner_context():
    r = _make_registry()
    ctx = r.get_planner_context()
    assert "agents" in ctx
    assert isinstance(ctx["agents"], list)
    assert len(ctx["agents"]) >= 9


def test_registry_planner_context_compact():
    r = _make_registry()
    compact = r.get_planner_context_compact()
    data = json.loads(compact)
    assert isinstance(data, list)
    assert len(data) >= 9


def test_registry_agent_info():
    r = _make_registry()
    info = r.get_agent_info("weather_agent")
    assert info is not None
    assert info["name"] == "weather_agent"
    assert "actions" in info


def test_registry_list_actions():
    r = _make_registry()
    actions = r.list_actions("todo_agent")
    assert "add_todo" in actions
    assert "list_all_todos" in actions


def test_registry_reload():
    r = _make_registry()
    count_before = len(r.list_agents())
    r.reload()
    count_after = len(r.list_agents())
    assert count_before == count_after


# ═══════════════════════════════════════════════════════════════════════════
# Schema Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_plan_schema_valid():
    plan = ExecutionPlan(
        requires_agents=True,
        parallel=False,
        tasks=[
            PlanTask(
                id="task_1",
                agent="gmail_agent",
                action="get_unread_emails",
                parameters={"limit": 5},
            )
        ],
    )
    assert plan.requires_agents is True
    assert len(plan.tasks) == 1
    assert plan.tasks[0].agent == "gmail_agent"


def test_plan_schema_no_agents():
    plan = ExecutionPlan(
        requires_agents=False,
        tasks=[],
        direct_response="Hello there!",
    )
    assert plan.requires_agents is False
    assert plan.direct_response == "Hello there!"


def test_plan_schema_requires_agents_no_tasks():
    import pytest
    with pytest.raises(Exception):
        ExecutionPlan(requires_agents=True, tasks=[])


def test_plan_schema_bad_dependency():
    import pytest
    with pytest.raises(Exception):
        ExecutionPlan(
            requires_agents=True,
            tasks=[
                PlanTask(
                    id="task_1",
                    agent="a",
                    action="b",
                    depends_on=["task_99"],
                )
            ],
        )


def test_plan_schema_self_dependency():
    import pytest
    with pytest.raises(Exception):
        ExecutionPlan(
            requires_agents=True,
            tasks=[
                PlanTask(
                    id="task_1",
                    agent="a",
                    action="b",
                    depends_on=["task_1"],
                )
            ],
        )


def test_plan_schema_with_dependencies():
    plan = ExecutionPlan(
        requires_agents=True,
        parallel=True,
        tasks=[
            PlanTask(id="task_1", agent="a", action="b"),
            PlanTask(id="task_2", agent="c", action="d", depends_on=["task_1"]),
        ],
    )
    assert plan.tasks[1].depends_on == ["task_1"]


def test_task_result_schema():
    result = TaskResult(
        task_id="t1",
        agent="gmail_agent",
        action="get_unread_emails",
        status=TaskStatus.COMPLETED,
        output={"data": []},
        duration_ms=123.4,
    )
    assert result.status == TaskStatus.COMPLETED
    d = result.model_dump()
    assert d["task_id"] == "t1"


# ═══════════════════════════════════════════════════════════════════════════
# Agent Loader Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_loader_loads_agent():
    r = _make_registry()
    loader = AgentLoader(r)
    module = loader.get_module("todo_agent")
    assert hasattr(module, "execute")
    assert hasattr(module, "PLUGIN_INFO")


def test_loader_execute_fn():
    r = _make_registry()
    loader = AgentLoader(r)
    fn = loader.get_execute_fn("todo_agent")
    assert callable(fn)


def test_loader_caching():
    r = _make_registry()
    loader = AgentLoader(r)
    m1 = loader.get_module("todo_agent")
    m2 = loader.get_module("todo_agent")
    assert m1 is m2


def test_loader_bad_agent():
    r = _make_registry()
    loader = AgentLoader(r)
    try:
        loader.get_module("nonexistent_agent")
        assert False, "Should have raised"
    except ImportError:
        pass


def test_loader_preload():
    r = _make_registry()
    loader = AgentLoader(r)
    results = loader.preload_all()
    assert len(results) >= 9
    for agent, error in results.items():
        assert error is None, f"Failed to load {agent}: {error}"


# ═══════════════════════════════════════════════════════════════════════════
# Work Queue Tests
# ═══════════════════════════════════════════════════════════════════════════

def _simple_plan() -> ExecutionPlan:
    return ExecutionPlan(
        requires_agents=True,
        parallel=False,
        tasks=[
            PlanTask(id="t1", agent="a", action="b"),
            PlanTask(id="t2", agent="c", action="d"),
        ],
    )


def _dependency_plan() -> ExecutionPlan:
    return ExecutionPlan(
        requires_agents=True,
        parallel=True,
        tasks=[
            PlanTask(id="t1", agent="a", action="b"),
            PlanTask(id="t2", agent="c", action="d", depends_on=["t1"]),
            PlanTask(id="t3", agent="e", action="f"),
        ],
    )


def test_queue_load():
    q = WorkQueue()
    q.load_plan(_simple_plan())
    assert q.task_count == 2
    assert not q.is_complete()


def test_queue_ready_no_deps():
    q = WorkQueue()
    q.load_plan(_simple_plan())
    ready = q.get_ready_tasks()
    assert len(ready) == 2


def test_queue_ready_with_deps():
    q = WorkQueue()
    q.load_plan(_dependency_plan())
    ready = q.get_ready_tasks()
    ids = {t.id for t in ready}
    assert "t1" in ids
    assert "t3" in ids
    assert "t2" not in ids


def test_queue_dependency_unlock():
    q = WorkQueue()
    q.load_plan(_dependency_plan())

    q.mark_running("t1")
    q.mark_completed(
        "t1",
        TaskResult(task_id="t1", agent="a", action="b", status=TaskStatus.COMPLETED),
    )

    ready = q.get_ready_tasks()
    ids = {t.id for t in ready}
    assert "t2" in ids


def test_queue_cancel_on_failure():
    q = WorkQueue()
    q.load_plan(_dependency_plan())

    q.mark_running("t1")
    q.mark_failed(
        "t1",
        TaskResult(
            task_id="t1", agent="a", action="b",
            status=TaskStatus.FAILED, error="boom",
        ),
    )

    summary = q.get_status_summary()
    assert summary.get("cancelled", 0) == 1


def test_queue_completion():
    q = WorkQueue()
    q.load_plan(_simple_plan())

    for task in q.get_ready_tasks():
        q.mark_running(task.id)
        q.mark_completed(
            task.id,
            TaskResult(
                task_id=task.id, agent=task.agent, action=task.action,
                status=TaskStatus.COMPLETED,
            ),
        )

    assert q.is_complete()
    assert len(q.get_all_results()) == 2


# ═══════════════════════════════════════════════════════════════════════════
# Executor Tests (with mocked agents)
# ═══════════════════════════════════════════════════════════════════════════

def _mock_execute_success(request: dict) -> dict:
    return {"status": "success", "action": request["action"], "data": {"mock": True}}


def _mock_execute_fail(request: dict) -> dict:
    return {"status": "error", "action": request["action"], "message": "mock fail"}


def test_executor_sequential():
    r = _make_registry()
    loader = AgentLoader(r)

    plan = ExecutionPlan(
        requires_agents=True,
        parallel=False,
        tasks=[
            PlanTask(id="t1", agent="todo_agent", action="list_all_todos", parameters={}),
        ],
    )

    with patch.object(loader, "get_execute_fn", return_value=_mock_execute_success):
        executor = AgentExecutor(r, loader, max_workers=2, task_timeout=10, max_retries=1)
        queue = WorkQueue()
        results = executor.execute_plan(plan, queue)

    assert len(results) == 1
    assert results[0].status == TaskStatus.COMPLETED


def test_executor_parallel():
    r = _make_registry()
    loader = AgentLoader(r)

    plan = ExecutionPlan(
        requires_agents=True,
        parallel=True,
        tasks=[
            PlanTask(id="t1", agent="todo_agent", action="list_all_todos", parameters={}),
            PlanTask(id="t2", agent="todo_agent", action="get_stats", parameters={}),
        ],
    )

    with patch.object(loader, "get_execute_fn", return_value=_mock_execute_success):
        executor = AgentExecutor(r, loader, max_workers=2, task_timeout=10, max_retries=1)
        queue = WorkQueue()
        results = executor.execute_plan(plan, queue)

    assert len(results) == 2
    assert all(r.status == TaskStatus.COMPLETED for r in results)


def test_executor_handles_failure():
    r = _make_registry()
    loader = AgentLoader(r)

    plan = ExecutionPlan(
        requires_agents=True,
        parallel=False,
        tasks=[
            PlanTask(id="t1", agent="todo_agent", action="list_all_todos", parameters={}),
        ],
    )

    with patch.object(loader, "get_execute_fn", return_value=_mock_execute_fail):
        executor = AgentExecutor(r, loader, max_workers=2, task_timeout=10, max_retries=0)
        queue = WorkQueue()
        results = executor.execute_plan(plan, queue)

    assert len(results) == 1
    assert results[0].status == TaskStatus.FAILED


def test_executor_with_dependencies():
    r = _make_registry()
    loader = AgentLoader(r)

    plan = ExecutionPlan(
        requires_agents=True,
        parallel=True,
        tasks=[
            PlanTask(id="t1", agent="todo_agent", action="list_all_todos", parameters={}),
            PlanTask(id="t2", agent="todo_agent", action="get_stats", parameters={}, depends_on=["t1"]),
        ],
    )

    call_order: list[str] = []

    def _tracking_execute(request: dict) -> dict:
        call_order.append(request["action"])
        return {"status": "success", "action": request["action"], "data": {}}

    with patch.object(loader, "get_execute_fn", return_value=_tracking_execute):
        executor = AgentExecutor(r, loader, max_workers=2, task_timeout=10, max_retries=0)
        queue = WorkQueue()
        results = executor.execute_plan(plan, queue)

    assert len(results) == 2
    assert call_order.index("list_all_todos") < call_order.index("get_stats")


def test_executor_dependency_failure_cancels():
    r = _make_registry()
    loader = AgentLoader(r)

    plan = ExecutionPlan(
        requires_agents=True,
        parallel=True,
        tasks=[
            PlanTask(id="t1", agent="todo_agent", action="list_all_todos", parameters={}),
            PlanTask(id="t2", agent="todo_agent", action="get_stats", parameters={}, depends_on=["t1"]),
        ],
    )

    with patch.object(loader, "get_execute_fn", return_value=_mock_execute_fail):
        executor = AgentExecutor(r, loader, max_workers=2, task_timeout=10, max_retries=0)
        queue = WorkQueue()
        results = executor.execute_plan(plan, queue)

    statuses = {r.task_id: r.status for r in results}
    assert statuses["t1"] == TaskStatus.FAILED
    assert statuses["t2"] == TaskStatus.CANCELLED


# ═══════════════════════════════════════════════════════════════════════════
# End-to-end Brain.process() tests (LLM mocked, full pipeline exercised)
# ═══════════════════════════════════════════════════════════════════════════

def _make_ollama_response(content: str):
    """Build a mock object matching ollama's chat response shape."""
    mock_resp = MagicMock()
    mock_resp.message.content = content
    return mock_resp


_DIRECT_PLAN_JSON = '{"requires_agents": false, "tasks": [], "direct_response": "Hello! How can I help you today?"}'

_AGENT_PLAN_JSON = json.dumps({
    "requires_agents": True,
    "parallel": False,
    "tasks": [
        {
            "id": "task_1",
            "agent": "todo_agent",
            "action": "list_all_todos",
            "parameters": {},
        }
    ],
})

_SPOKEN_RESPONSE = "Here are your todos."


def test_brain_e2e_direct_response():
    """Full pipeline: greeting → planner returns direct_response → spoken text."""
    with patch("brain.planner._call_ollama", return_value=_DIRECT_PLAN_JSON):
        brain = __import__("brain.brain", fromlist=["Brain"]).Brain(
            enable_memory=False, preload_agents=False,
        )
        response = brain.process("Hello")

    assert "Hello" in response or "help" in response.lower()


def test_brain_e2e_agent_plan():
    """Full pipeline: command → planner → executor (mocked agent) → response."""
    with patch("brain.planner._call_ollama", return_value=_AGENT_PLAN_JSON), \
         patch("brain.response_generator._call_ollama", return_value=_SPOKEN_RESPONSE):

        brain = __import__("brain.brain", fromlist=["Brain"]).Brain(
            enable_memory=False, preload_agents=False,
        )

        with patch.object(brain.executor._loader, "get_execute_fn", return_value=_mock_execute_success):
            response = brain.process("Show my todos")

    assert response
    assert "todos" in response.lower() or len(response) > 0


def test_brain_e2e_process_raw():
    """process_raw returns structured output with plan + results."""
    with patch("brain.planner._call_ollama", return_value=_AGENT_PLAN_JSON), \
         patch("brain.response_generator._call_ollama", return_value=_SPOKEN_RESPONSE):

        brain = __import__("brain.brain", fromlist=["Brain"]).Brain(
            enable_memory=False, preload_agents=False,
        )

        with patch.object(brain.executor._loader, "get_execute_fn", return_value=_mock_execute_success):
            raw = brain.process_raw("Show my todos")

    assert raw["status"] == "success"
    assert raw["path"] == "agent"
    assert len(raw["results"]) == 1
    assert raw["response"]


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

def _run_all() -> int:
    """Run all test_* functions, report results."""
    tests = [
        (name, func)
        for name, func in sorted(globals().items())
        if name.startswith("test_") and callable(func)
    ]

    passed = failed = 0
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
