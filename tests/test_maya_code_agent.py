"""Tests for Maya Code Agent — covers all acceptance criteria.

Run with:  pytest tests/test_maya_code_agent.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
import textwrap
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_project(tmp_path):
    """Create a minimal project directory."""
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "requirements.txt").write_text("requests\n")
    (tmp_path / "README.md").write_text("# Test Project\n")
    return tmp_path


@pytest.fixture
def _reset_store():
    """Reset the global job store between tests."""
    from agents.maya_code.runner import _store
    _store._jobs.clear()
    yield
    _store._jobs.clear()


# ── 1. PLUGIN_INFO is valid ──────────────────────────────────────────────────

class TestPluginInfo:
    def test_required_fields(self):
        from agents.maya_code_agent import PLUGIN_INFO
        assert PLUGIN_INFO["name"] == "maya_code_agent"
        assert PLUGIN_INFO["entrypoint"] == "execute"
        assert PLUGIN_INFO["type"] == "tool"
        assert PLUGIN_INFO["input_format"] == "json"
        assert PLUGIN_INFO["output_format"] == "json"

    def test_voice_disabled(self):
        from agents.maya_code_agent import PLUGIN_INFO
        assert PLUGIN_INFO.get("voice_enabled") is False

    def test_has_keywords(self):
        from agents.maya_code_agent import PLUGIN_INFO
        assert len(PLUGIN_INFO.get("keywords", [])) > 0


# ── 2. execute() dispatch ────────────────────────────────────────────────────

class TestExecuteDispatch:
    def test_missing_action(self):
        from agents.maya_code_agent import execute
        r = execute({})
        assert r["status"] == "error"
        assert "action" in r["message"].lower()

    def test_unknown_action(self):
        from agents.maya_code_agent import execute
        r = execute({"action": "fly_to_moon"})
        assert r["status"] == "error"
        assert "fly_to_moon" in r["message"]

    def test_missing_required_params(self):
        from agents.maya_code_agent import execute
        r = execute({"action": "start_task", "parameters": {}})
        assert r["status"] == "error"
        assert "goal" in r["message"]

    def test_list_jobs_empty(self, _reset_store):
        from agents.maya_code_agent import execute
        r = execute({"action": "list_jobs", "parameters": {}})
        assert r["status"] == "success"
        assert r["data"]["jobs"] == []


# ── 3. State machine ─────────────────────────────────────────────────────────

class TestStateMachine:
    def test_valid_transitions(self):
        from agents.maya_code.state_machine import PhaseMachine
        from agents.maya_code.contracts import Phase
        m = PhaseMachine()
        assert m.phase == Phase.ANALYZING
        m.transition(Phase.PLANNING)
        assert m.phase == Phase.PLANNING
        m.transition(Phase.EXECUTING)
        m.transition(Phase.VERIFYING)
        m.transition(Phase.DONE)
        assert m.phase == Phase.DONE

    def test_invalid_transition_raises(self):
        from agents.maya_code.state_machine import PhaseMachine, IllegalTransition
        from agents.maya_code.contracts import Phase
        m = PhaseMachine()
        with pytest.raises(IllegalTransition):
            m.transition(Phase.EXECUTING)  # can't skip PLANNING

    def test_fixing_loop(self):
        from agents.maya_code.state_machine import PhaseMachine
        from agents.maya_code.contracts import Phase
        m = PhaseMachine()
        m.transition(Phase.PLANNING)
        m.transition(Phase.EXECUTING)
        m.transition(Phase.VERIFYING)
        m.transition(Phase.FIXING)
        m.transition(Phase.EXECUTING)
        m.transition(Phase.VERIFYING)
        m.transition(Phase.DONE)

    def test_force_terminal(self):
        from agents.maya_code.state_machine import PhaseMachine
        from agents.maya_code.contracts import Phase
        m = PhaseMachine()
        m.force_terminal(Phase.DONE)
        assert m.phase == Phase.DONE


# ── 4. Validators ────────────────────────────────────────────────────────────

class TestValidators:
    def test_empty_project_root(self):
        from agents.maya_code.validators import validate_project_root, ValidationError
        with pytest.raises(ValidationError, match="required"):
            validate_project_root("")

    def test_nonexistent_root(self):
        from agents.maya_code.validators import validate_project_root, ValidationError
        with pytest.raises(ValidationError, match="does not exist"):
            validate_project_root("/nonexistent/path/xyz123")

    def test_valid_root(self, temp_project):
        from agents.maya_code.validators import validate_project_root
        result = validate_project_root(str(temp_project))
        assert result == temp_project.resolve()

    def test_path_escape_blocked(self, temp_project):
        from agents.maya_code.validators import validate_path_in_root, ValidationError
        with pytest.raises(ValidationError, match="escapes"):
            validate_path_in_root("../../etc/passwd", temp_project)

    def test_path_inside_root(self, temp_project):
        from agents.maya_code.validators import validate_path_in_root
        result = validate_path_in_root("main.py", temp_project)
        assert result == (temp_project / "main.py").resolve()

    def test_command_denylist(self, temp_project):
        from agents.maya_code.validators import validate_command, ValidationError
        with pytest.raises(ValidationError, match="denylist"):
            validate_command("rm -rf /", temp_project)

    def test_command_allowlist(self, temp_project):
        from agents.maya_code.validators import validate_command
        result = validate_command("python main.py", temp_project)
        assert "python" in result

    def test_command_not_allowed(self, temp_project):
        from agents.maya_code.validators import validate_command, ValidationError
        with pytest.raises(ValidationError, match="allowlist"):
            validate_command("evil_binary --destroy", temp_project)

    def test_file_size_limit(self):
        from agents.maya_code.validators import validate_file_size, ValidationError
        huge = "x" * (3 * 1024 * 1024)  # 3MB exceeds 2MB limit
        with pytest.raises(ValidationError, match="exceeding"):
            validate_file_size(huge)


# ── 5. Contracts (Pydantic) ──────────────────────────────────────────────────

class TestContracts:
    def test_status_snapshot_defaults(self):
        from agents.maya_code.contracts import StatusSnapshot, JobState, Phase
        snap = StatusSnapshot(job_id="test_1")
        assert snap.state == JobState.PENDING
        assert snap.phase == Phase.ANALYZING
        assert snap.done is False

    def test_plan_step_validation(self):
        from agents.maya_code.contracts import PlanStep, StepAction
        step = PlanStep(id=1, description="Create file", action=StepAction.CREATE_FILE,
                        target="hello.py", content="print('hi')")
        assert step.confidence == 0.8

    def test_plan_step_bad_confidence(self):
        from agents.maya_code.contracts import PlanStep, StepAction
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PlanStep(id=1, description="x", action=StepAction.CREATE_FILE, confidence=2.0)


# ── 6. Analyzer ──────────────────────────────────────────────────────────────

class TestAnalyzer:
    def test_detect_python_project(self, temp_project):
        from agents.maya_code.analyzer import analyze_project
        analysis = analyze_project(temp_project)
        assert analysis.project_type == "python"
        assert "Python" in analysis.languages
        assert "requirements.txt" in analysis.dependency_files

    def test_file_tree_populated(self, temp_project):
        from agents.maya_code.analyzer import analyze_project
        analysis = analyze_project(temp_project)
        assert len(analysis.file_tree) >= 2

    def test_format_for_llm(self, temp_project):
        from agents.maya_code.analyzer import analyze_project, format_analysis_for_llm
        analysis = analyze_project(temp_project)
        text = format_analysis_for_llm(analysis)
        assert "python" in text.lower()
        assert "main.py" in text


# ── 7. Checkpoint ────────────────────────────────────────────────────────────

class TestCheckpoint:
    def test_save_and_rollback(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        cp = CheckpointManager("test_cp", temp_project)
        target = temp_project / "main.py"
        original = target.read_text()

        cp.save(target)
        target.write_text("modified content")
        assert target.read_text() == "modified content"

        log = cp.rollback()
        assert target.read_text() == original
        assert any("Restored" in l for l in log)
        cp.cleanup()

    def test_rollback_new_file(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        cp = CheckpointManager("test_new", temp_project)
        new_file = temp_project / "brand_new.py"

        cp.save(new_file)
        new_file.write_text("new content")
        assert new_file.exists()

        log = cp.rollback()
        assert not new_file.exists()
        cp.cleanup()


# ── 8. Executor ──────────────────────────────────────────────────────────────

class TestExecutor:
    def test_create_file(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.executor import StepExecutor
        from agents.maya_code.contracts import PlanStep, StepAction

        cp = CheckpointManager("test_exec", temp_project)
        executor = StepExecutor(temp_project, cp)
        step = PlanStep(id=1, description="Create file", action=StepAction.CREATE_FILE,
                        target="new_file.py", content="print('created')")

        result = executor.execute_step(step)
        assert result.success
        assert (temp_project / "new_file.py").exists()
        cp.cleanup()

    def test_create_file_dry_run(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.executor import StepExecutor
        from agents.maya_code.contracts import PlanStep, StepAction

        cp = CheckpointManager("test_dry", temp_project)
        executor = StepExecutor(temp_project, cp, dry_run=True)
        step = PlanStep(id=1, description="Create file", action=StepAction.CREATE_FILE,
                        target="dry.py", content="print('dry')")

        result = executor.execute_step(step)
        assert result.success
        assert not (temp_project / "dry.py").exists()
        cp.cleanup()

    def test_path_escape_blocked(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.executor import StepExecutor
        from agents.maya_code.contracts import PlanStep, StepAction

        cp = CheckpointManager("test_escape", temp_project)
        executor = StepExecutor(temp_project, cp)
        step = PlanStep(id=1, description="Escape", action=StepAction.CREATE_FILE,
                        target="../../evil.py", content="import os; os.system('evil')")

        result = executor.execute_step(step)
        assert not result.success
        assert "escape" in (result.error or "").lower() or "validation" in (result.error or "").lower()
        cp.cleanup()

    def test_denied_command(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.executor import StepExecutor
        from agents.maya_code.contracts import PlanStep, StepAction

        cp = CheckpointManager("test_deny", temp_project)
        executor = StepExecutor(temp_project, cp)
        step = PlanStep(id=1, description="Evil", action=StepAction.RUN_COMMAND,
                        command="rm -rf /")

        result = executor.execute_step(step)
        assert not result.success
        assert "denylist" in (result.error or "").lower() or "blocked" in (result.error or "").lower()
        cp.cleanup()


# ── 9. Job store ─────────────────────────────────────────────────────────────

class TestJobStore:
    def test_create_and_get(self, _reset_store):
        from agents.maya_code.job_store import JobStore
        from agents.maya_code.contracts import JobState
        store = JobStore()
        snap = store.create("j1", "test goal")
        assert snap.job_id == "j1"
        assert snap.state == JobState.PENDING

        retrieved = store.get("j1")
        assert retrieved is not None
        assert retrieved.goal == "test goal"

    def test_update(self, _reset_store):
        from agents.maya_code.job_store import JobStore
        from agents.maya_code.contracts import JobState
        store = JobStore()
        store.create("j2", "test")
        store.update("j2", state=JobState.RUNNING, log_line="started")
        snap = store.get("j2")
        assert snap.state == JobState.RUNNING
        assert "started" in snap.log_tail

    def test_cancel(self, _reset_store):
        from agents.maya_code.job_store import JobStore
        from agents.maya_code.contracts import JobState
        store = JobStore()
        store.create("j3", "cancel me")
        snap = store.cancel("j3")
        assert snap.state == JobState.CANCELLED
        assert snap.done is True

    def test_unknown_job(self, _reset_store):
        from agents.maya_code.job_store import JobStore
        store = JobStore()
        assert store.get("nonexistent") is None


# ── 10. Config ───────────────────────────────────────────────────────────────

class TestConfig:
    def test_defaults(self):
        from agents.maya_code import config
        assert config.MAX_ITERATIONS == 30
        assert config.COMMAND_TIMEOUT == 60
        assert config.MAX_FILE_SIZE == 2 * 1024 * 1024

    def test_feature_flag(self):
        from agents.maya_code import config
        assert isinstance(config.ENABLED, bool)

    def test_model_chain(self):
        from agents.maya_code import config
        assert config.MODEL_PRIMARY
        assert config.MODEL_FALLBACK
        assert config.MODEL_FALLBACK_2

    def test_denylist_entries(self):
        from agents.maya_code import config
        assert "rm -rf /" in config.COMMAND_DENYLIST
        assert "mkfs" in config.COMMAND_DENYLIST


# ── 11. Feature flag (disabled) ──────────────────────────────────────────────

class TestFeatureFlag:
    def test_disabled_returns_error(self, temp_project):
        from agents.maya_code import config
        original = config.ENABLED
        try:
            config.ENABLED = False
            from agents.maya_code.runner import start_task
            r = start_task("test", str(temp_project))
            assert r["status"] == "error"
            assert "disabled" in r["message"].lower()
        finally:
            config.ENABLED = original


# ── 12. Dry run ──────────────────────────────────────────────────────────────

class TestDryRun:
    @patch("agents.maya_code.runner.call_llm_structured")
    def test_dry_run_no_file_changes(self, mock_llm, temp_project, _reset_store):
        from agents.maya_code.contracts import LLMPlanResponse, PlanStep, StepAction
        from agents.maya_code.runner import start_task, get_status

        mock_plan = LLMPlanResponse(
            goal="test", summary="test plan",
            steps=[PlanStep(id=1, description="Create file", action=StepAction.CREATE_FILE,
                            target="test.py", content="print('hi')")],
        )
        mock_llm.return_value = (mock_plan, "test-model")

        r = start_task("test", str(temp_project), dry_run=True)
        assert r["status"] == "success"
        job_id = r["data"]["job_id"]

        # wait for completion
        for _ in range(50):
            time.sleep(0.1)
            status = get_status(job_id)
            if status["data"]["done"]:
                break

        assert not (temp_project / "test.py").exists()
        assert "dry run" in (status["data"].get("summary") or "").lower()


# ── 13. Project-root jail ────────────────────────────────────────────────────

class TestProjectRootJail:
    def test_maya_dir_blocked(self):
        from agents.maya_code.validators import validate_project_root, ValidationError
        from agents.maya_code import config
        maya_root = str(config.PROJECT_ROOT)
        with pytest.raises(ValidationError, match="Maya"):
            validate_project_root(maya_root)

    def test_external_project_allowed(self, temp_project):
        from agents.maya_code.validators import validate_project_root
        result = validate_project_root(str(temp_project))
        assert result == temp_project.resolve()


# ═════════════════════════════════════════════════════════════════════════════
#  v2 Tests
# ═════════════════════════════════════════════════════════════════════════════

# ── 14. v2 Contracts ────────────────────────────────────────────────────────

class TestContractsV2:
    def test_tool_name_values(self):
        from agents.maya_code.contracts import ToolName
        assert ToolName.READ_FILE.value == "read_file"
        assert ToolName.EDIT_FILE.value == "edit_file"
        assert ToolName.DONE.value == "done"

    def test_tool_call_defaults(self):
        from agents.maya_code.contracts import ToolCall, ToolName
        tc = ToolCall(tool=ToolName.READ_FILE, args={"path": "main.py"})
        assert tc.reasoning == ""
        assert tc.args["path"] == "main.py"

    def test_subtask_defaults(self):
        from agents.maya_code.contracts import Subtask, SubtaskState
        st = Subtask(id="st_001", title="Test")
        assert st.state == SubtaskState.PENDING
        assert st.action_budget == 30
        assert st.actions_used == 0
        assert st.action_history == []

    def test_subtask_graph_serializes(self):
        from agents.maya_code.contracts import Subtask, SubtaskGraph
        graph = SubtaskGraph(
            goal="Build API",
            subtasks=[Subtask(id="st_001", title="Models"), Subtask(id="st_002", title="Routes", depends_on=["st_001"])],
            execution_order=["st_001", "st_002"],
        )
        data = graph.model_dump()
        assert len(data["subtasks"]) == 2
        assert data["execution_order"] == ["st_001", "st_002"]

    def test_parsed_goal_defaults(self):
        from agents.maya_code.contracts import ParsedGoal, ScopeEstimate
        pg = ParsedGoal(raw="Build something")
        assert pg.scope == ScopeEstimate.M
        assert pg.key_files == []

    def test_status_snapshot_v2_fields(self):
        from agents.maya_code.contracts import StatusSnapshot
        snap = StatusSnapshot(job_id="test_123")
        assert snap.version == "v1"
        assert snap.subtasks is None
        assert snap.total_subtasks == 0
        snap.version = "v2"
        snap.subtasks = [{"id": "st_001", "title": "Test", "state": "RUNNING"}]
        assert snap.version == "v2"

    def test_scope_estimate_values(self):
        from agents.maya_code.contracts import ScopeEstimate
        assert ScopeEstimate.S.value == "S"
        assert ScopeEstimate.XL.value == "XL"


# ── 15. ToolBelt ────────────────────────────────────────────────────────────

class TestToolBelt:
    def test_read_file(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import ToolCall, ToolName

        cp = CheckpointManager("test_tb", temp_project)
        belt = ToolBelt(temp_project, cp)
        result = belt.execute(ToolCall(tool=ToolName.READ_FILE, args={"path": "main.py"}))
        assert result.success
        assert "hello" in result.output
        assert "main.py" in belt.file_cache
        cp.cleanup()

    def test_read_file_not_found(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import ToolCall, ToolName

        cp = CheckpointManager("test_tb2", temp_project)
        belt = ToolBelt(temp_project, cp)
        result = belt.execute(ToolCall(tool=ToolName.READ_FILE, args={"path": "nope.py"}))
        assert not result.success
        assert "not found" in result.error.lower()
        cp.cleanup()

    def test_write_file(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import ToolCall, ToolName

        cp = CheckpointManager("test_tb3", temp_project)
        belt = ToolBelt(temp_project, cp)
        result = belt.execute(ToolCall(tool=ToolName.WRITE_FILE, args={"path": "new.py", "content": "x = 1\n"}))
        assert result.success
        assert (temp_project / "new.py").read_text() == "x = 1\n"
        cp.cleanup()

    def test_edit_file_search_replace(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import ToolCall, ToolName

        cp = CheckpointManager("test_tb4", temp_project)
        belt = ToolBelt(temp_project, cp)
        result = belt.execute(ToolCall(tool=ToolName.EDIT_FILE, args={
            "path": "main.py",
            "search": "print('hello')",
            "replace": "print('world')",
        }))
        assert result.success
        assert "world" in (temp_project / "main.py").read_text()
        cp.cleanup()

    def test_edit_file_not_found_search(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import ToolCall, ToolName

        cp = CheckpointManager("test_tb5", temp_project)
        belt = ToolBelt(temp_project, cp)
        result = belt.execute(ToolCall(tool=ToolName.EDIT_FILE, args={
            "path": "main.py",
            "search": "nonexistent_string_xyz",
            "replace": "something",
        }))
        assert not result.success
        assert "not found" in result.error.lower()
        cp.cleanup()

    def test_edit_file_ambiguous(self, temp_project):
        (temp_project / "dups.py").write_text("x = 1\nx = 1\n")
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import ToolCall, ToolName

        cp = CheckpointManager("test_tb6", temp_project)
        belt = ToolBelt(temp_project, cp)
        result = belt.execute(ToolCall(tool=ToolName.EDIT_FILE, args={
            "path": "dups.py",
            "search": "x = 1",
            "replace": "x = 2",
        }))
        assert not result.success
        assert "2 times" in result.error
        cp.cleanup()

    def test_list_files(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import ToolCall, ToolName

        cp = CheckpointManager("test_tb7", temp_project)
        belt = ToolBelt(temp_project, cp)
        result = belt.execute(ToolCall(tool=ToolName.LIST_FILES, args={"path": "."}))
        assert result.success
        assert "main.py" in result.output
        cp.cleanup()

    def test_done_tool(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import ToolCall, ToolName

        cp = CheckpointManager("test_tb8", temp_project)
        belt = ToolBelt(temp_project, cp)
        result = belt.execute(ToolCall(tool=ToolName.DONE, args={"summary": "All done"}))
        assert result.success
        assert result.output == "All done"
        cp.cleanup()

    def test_path_escape_blocked(self, temp_project):
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import ToolCall, ToolName

        cp = CheckpointManager("test_tb9", temp_project)
        belt = ToolBelt(temp_project, cp)
        result = belt.execute(ToolCall(tool=ToolName.READ_FILE, args={"path": "../../etc/passwd"}))
        assert not result.success
        assert "Validation" in result.error or "escape" in result.error.lower()
        cp.cleanup()


# ── 16. Context Window ─────────────────────────────────────────────────────

class TestContextWindow:
    def test_assemble_produces_prompt(self):
        from agents.maya_code.context_window import assemble_context
        from agents.maya_code.contracts import ParsedGoal, Subtask, ScopeEstimate

        goal = ParsedGoal(raw="Add auth", refined="Add JWT authentication", scope=ScopeEstimate.M,
                          acceptance_criteria=["Login works", "Token validated"])
        subtask = Subtask(id="st_001", title="Create JWT middleware", action_budget=30)

        system, user = assemble_context(goal, subtask, {}, [])
        assert "tool" in system.lower()
        assert "JWT" in user
        assert "middleware" in user.lower()

    def test_file_cache_included(self):
        from agents.maya_code.context_window import assemble_context
        from agents.maya_code.contracts import ParsedGoal, Subtask, ScopeEstimate

        goal = ParsedGoal(raw="Fix bug", scope=ScopeEstimate.S)
        subtask = Subtask(id="st_001", title="Fix it", action_budget=15)
        cache = {"src/app.py": "from flask import Flask\napp = Flask(__name__)\n"}

        system, user = assemble_context(goal, subtask, cache, [])
        assert "app.py" in user
        assert "Flask" in user

    def test_action_summary(self):
        from agents.maya_code.context_window import summarize_action
        from agents.maya_code.contracts import ActionRecord, ToolCall, ToolResult, ToolName

        record = ActionRecord(
            iteration=3,
            tool_call=ToolCall(tool=ToolName.READ_FILE, args={"path": "src/app.py"}),
            tool_result=ToolResult(tool=ToolName.READ_FILE, success=True, output="content"),
            timestamp="2025-01-01T00:00:00Z",
        )
        summary = summarize_action(record)
        assert "[3]" in summary
        assert "read_file" in summary
        assert "app.py" in summary
        assert "OK" in summary


# ── 17. Decomposer (topological sort) ──────────────────────────────────────

class TestDecomposer:
    def test_topological_sort_simple(self):
        from agents.maya_code.decomposer import _topological_sort
        from agents.maya_code.contracts import Subtask

        subtasks = [
            Subtask(id="a", title="A"),
            Subtask(id="b", title="B", depends_on=["a"]),
            Subtask(id="c", title="C", depends_on=["b"]),
        ]
        order = _topological_sort(subtasks)
        assert order == ["a", "b", "c"]

    def test_topological_sort_diamond(self):
        from agents.maya_code.decomposer import _topological_sort
        from agents.maya_code.contracts import Subtask

        subtasks = [
            Subtask(id="a", title="A"),
            Subtask(id="b", title="B", depends_on=["a"]),
            Subtask(id="c", title="C", depends_on=["a"]),
            Subtask(id="d", title="D", depends_on=["b", "c"]),
        ]
        order = _topological_sort(subtasks)
        assert order is not None
        assert order[0] == "a"
        assert order[-1] == "d"
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_cycle_detected(self):
        from agents.maya_code.decomposer import _topological_sort
        from agents.maya_code.contracts import Subtask

        subtasks = [
            Subtask(id="a", title="A", depends_on=["c"]),
            Subtask(id="b", title="B", depends_on=["a"]),
            Subtask(id="c", title="C", depends_on=["b"]),
        ]
        order = _topological_sort(subtasks)
        assert order is None

    def test_single_subtask_fallback(self):
        from agents.maya_code.decomposer import _single_subtask_fallback
        from agents.maya_code.contracts import ParsedGoal, ScopeEstimate

        goal = ParsedGoal(raw="Fix bug", scope=ScopeEstimate.S)
        graph = _single_subtask_fallback(goal)
        assert len(graph.subtasks) == 1
        assert graph.execution_order == ["st_001"]


# ── 18. Agentic Loop (mocked LLM) ──────────────────────────────────────────

class TestAgenticLoop:
    def test_loop_completes_on_done(self, temp_project):
        from agents.maya_code.agentic_loop import run_subtask
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import (
            ParsedGoal, Subtask, SubtaskState, ScopeEstimate,
            ToolCall, ToolName,
        )

        cp = CheckpointManager("test_loop", temp_project)
        belt = ToolBelt(temp_project, cp)
        goal = ParsedGoal(raw="Test", scope=ScopeEstimate.S)
        subtask = Subtask(id="st_001", title="Read and done", action_budget=10)
        logs = []

        call_sequence = [
            ToolCall(tool=ToolName.READ_FILE, args={"path": "main.py"}, reasoning="Read first"),
            ToolCall(tool=ToolName.DONE, args={"summary": "All good"}, reasoning="Done"),
        ]
        call_iter = iter(call_sequence)

        def mock_llm(system, user, schema, **kwargs):
            return (next(call_iter), "test-model")

        with patch("agents.maya_code.agentic_loop.call_llm_structured", side_effect=mock_llm):
            result = run_subtask(subtask, goal, "", belt, logs.append, lambda: False)

        assert result.state == SubtaskState.COMPLETED
        assert result.summary == "All good"
        assert result.actions_used == 2
        assert len(result.action_history) == 2
        cp.cleanup()

    def test_loop_stops_on_budget(self, temp_project):
        from agents.maya_code.agentic_loop import run_subtask
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import (
            ParsedGoal, Subtask, SubtaskState, ScopeEstimate,
            ToolCall, ToolName,
        )

        cp = CheckpointManager("test_loop2", temp_project)
        belt = ToolBelt(temp_project, cp)
        goal = ParsedGoal(raw="Test", scope=ScopeEstimate.S)
        subtask = Subtask(id="st_001", title="Infinite reader", action_budget=3)

        def mock_llm(system, user, schema, **kwargs):
            return (ToolCall(tool=ToolName.LIST_FILES, args={"path": "."}, reasoning="Exploring"), "test-model")

        with patch("agents.maya_code.agentic_loop.call_llm_structured", side_effect=mock_llm):
            result = run_subtask(subtask, goal, "", belt, lambda m: None, lambda: False)

        assert result.state == SubtaskState.FAILED
        assert "budget" in result.error.lower()
        assert result.actions_used == 3
        cp.cleanup()

    def test_loop_stops_on_cancel(self, temp_project):
        from agents.maya_code.agentic_loop import run_subtask
        from agents.maya_code.checkpoint import CheckpointManager
        from agents.maya_code.tool_executor import ToolBelt
        from agents.maya_code.contracts import (
            ParsedGoal, Subtask, SubtaskState, ScopeEstimate,
            ToolCall, ToolName,
        )

        cp = CheckpointManager("test_loop3", temp_project)
        belt = ToolBelt(temp_project, cp)
        goal = ParsedGoal(raw="Test", scope=ScopeEstimate.S)
        subtask = Subtask(id="st_001", title="Cancel test", action_budget=10)

        def mock_llm(system, user, schema, **kwargs):
            return (ToolCall(tool=ToolName.LIST_FILES, args={"path": "."}, reasoning="Go"), "test-model")

        with patch("agents.maya_code.agentic_loop.call_llm_structured", side_effect=mock_llm):
            result = run_subtask(subtask, goal, "", belt, lambda m: None, lambda: True)

        assert result.state == SubtaskState.FAILED
        assert "cancel" in result.error.lower()
        cp.cleanup()


# ── 19. v2 Config ──────────────────────────────────────────────────────────

class TestConfigV2:
    def test_v2_defaults(self):
        from agents.maya_code import config
        assert config.V2_MAX_SUBTASKS == 10
        assert config.V2_MAX_ACTIONS_S == 15
        assert config.V2_MAX_ACTIONS_M == 30
        assert config.V2_MAX_ACTIONS_L == 50
        assert config.V2_MAX_ACTIONS_XL == 80
        assert config.V2_CONTEXT_WINDOW_CHARS == 48000

    def test_scope_budget_map(self):
        from agents.maya_code import config
        assert config.SCOPE_BUDGET_MAP["S"] == 15
        assert config.SCOPE_BUDGET_MAP["XL"] == 80


# ── 20. v1 Fallback ───────────────────────────────────────────────────────

class TestV1Fallback:
    def test_scope_s_uses_v1(self, temp_project, _reset_store):
        """Scope S should use v1 fast path (no decomposition)."""
        from agents.maya_code.contracts import (
            LLMGoalParseResponse, LLMPlanResponse, PlanStep, StepAction,
        )

        mock_goal_parse = LLMGoalParseResponse(
            refined="Simple fix", scope="S", key_files=[], acceptance_criteria=[]
        )
        mock_plan = LLMPlanResponse(
            goal="Simple fix", summary="One step",
            steps=[PlanStep(id=1, description="Create file", action=StepAction.CREATE_FILE,
                            target="test_out.txt", content="done", expected_outcome="file exists")],
        )

        def mock_goal_parser(goal, analysis):
            from agents.maya_code.contracts import ParsedGoal, ScopeEstimate
            return ParsedGoal(raw=goal, refined="Simple fix", scope=ScopeEstimate.S)

        def mock_llm(system, user, schema, **kwargs):
            if schema.__name__ == "LLMPlanResponse":
                return (mock_plan, "test-model")
            return (mock_goal_parse, "test-model")

        with patch("agents.maya_code.runner.call_llm_structured", side_effect=mock_llm), \
             patch("agents.maya_code.goal_parser.call_llm_structured", side_effect=mock_llm):
            from agents.maya_code.runner import start_task
            result = start_task(goal="Simple fix", project_root=str(temp_project))
            assert result["status"] == "success"

            # Wait for thread
            import time
            time.sleep(2)

            from agents.maya_code.runner import get_status
            status = get_status(result["data"]["job_id"])
            # Should complete via v1 (no subtasks field or version stays v1)
            assert status["status"] == "success"
            data = status["data"]
            assert data["done"] is True


# ── 21. Small Model Robustness (JSON repair, fuzzy matching) ────────────────

class TestSmallModelRobustness:
    """Tests that smaller/weaker models can still drive the agent."""

    def test_tool_name_aliases(self):
        from agents.maya_code.models import _normalize_tool_name
        assert _normalize_tool_name("read") == "read_file"
        assert _normalize_tool_name("write") == "write_file"
        assert _normalize_tool_name("edit") == "edit_file"
        assert _normalize_tool_name("run") == "run_cmd"
        assert _normalize_tool_name("search") == "search_code"
        assert _normalize_tool_name("list") == "list_files"
        assert _normalize_tool_name("test") == "run_tests"
        assert _normalize_tool_name("finish") == "done"
        assert _normalize_tool_name("complete") == "done"
        assert _normalize_tool_name("READ_FILE") == "read_file"
        assert _normalize_tool_name("readFile") == "read_file"
        assert _normalize_tool_name("cat") == "read_file"
        assert _normalize_tool_name("grep") == "search_code"
        assert _normalize_tool_name("ls") == "list_files"
        assert _normalize_tool_name("create_file") == "write_file"
        assert _normalize_tool_name("modify_file") == "edit_file"

    def test_json_repair_trailing_comma(self):
        from agents.maya_code.models import _repair_json
        bad = '{"tool": "read_file", "args": {"path": "x.py",},}'
        fixed = _repair_json(bad)
        data = json.loads(fixed)
        assert data["tool"] == "read_file"

    def test_json_repair_single_quotes(self):
        from agents.maya_code.models import _repair_json
        bad = "{'tool': 'read_file', 'args': {'path': 'x.py'}}"
        fixed = _repair_json(bad)
        data = json.loads(fixed)
        assert data["tool"] == "read_file"

    def test_json_repair_unquoted_keys(self):
        from agents.maya_code.models import _repair_json
        bad = '{tool: "read_file", args: {"path": "x.py"}}'
        fixed = _repair_json(bad)
        data = json.loads(fixed)
        assert data["tool"] == "read_file"

    def test_json_repair_python_booleans(self):
        from agents.maya_code.models import _repair_json
        bad = '{"success": True, "error": None}'
        fixed = _repair_json(bad)
        data = json.loads(fixed)
        assert data["success"] is True
        assert data["error"] is None

    def test_normalize_data_alt_field_names(self):
        from agents.maya_code.models import _normalize_data
        from agents.maya_code.contracts import ToolCall

        # "action" instead of "tool", "parameters" instead of "args"
        data = {"action": "read", "parameters": {"path": "x.py"}, "reason": "need to see"}
        normalized = _normalize_data(data, ToolCall)
        assert normalized["tool"] == "read_file"
        assert normalized["args"] == {"path": "x.py"}
        assert normalized["reasoning"] == "need to see"

    def test_normalize_data_flat_args(self):
        from agents.maya_code.models import _normalize_data
        from agents.maya_code.contracts import ToolCall

        # Model puts path at top level instead of inside args
        data = {"tool": "read", "path": "x.py", "reasoning": "check"}
        normalized = _normalize_data(data, ToolCall)
        assert normalized["tool"] == "read_file"
        assert normalized["args"]["path"] == "x.py"

    def test_try_parse_messy_output(self):
        from agents.maya_code.models import _try_parse
        from agents.maya_code.contracts import ToolCall

        # Simulates messy LLM output with markdown fence and alias
        raw = """Sure! Here's my action:
```json
{action: 'read', parameters: {path: 'main.py'}, reason: 'checking code'}
```
"""
        parsed = _try_parse(raw, ToolCall)
        assert parsed.tool.value == "read_file"
        assert parsed.args["path"] == "main.py"
        assert parsed.reasoning == "checking code"

    def test_try_parse_clean_json(self):
        from agents.maya_code.models import _try_parse
        from agents.maya_code.contracts import ToolCall

        raw = '{"tool": "done", "args": {"summary": "finished"}, "reasoning": "all done"}'
        parsed = _try_parse(raw, ToolCall)
        assert parsed.tool.value == "done"
        assert parsed.args["summary"] == "finished"

    def test_normalize_subtask_deps_aliases(self):
        from agents.maya_code.models import _normalize_data
        from agents.maya_code.contracts import LLMDecompositionResponse

        data = {"subtasks": [
            {"id": "st_001", "title": "A", "description": "do A", "dependencies": ["st_000"], "scope": "S"},
            {"id": "st_002", "title": "B", "description": "do B", "deps": [], "scope": "M"},
        ]}
        normalized = _normalize_data(data, LLMDecompositionResponse)
        assert normalized["subtasks"][0]["depends_on"] == ["st_000"]
        assert normalized["subtasks"][1]["depends_on"] == []


# ── 22. Budget warning in context window ───────────────────────────────────

class TestBudgetWarning:
    def test_warning_at_70_percent(self):
        from agents.maya_code.context_window import assemble_context
        from agents.maya_code.contracts import ParsedGoal, Subtask, ScopeEstimate

        goal = ParsedGoal(raw="Build app", scope=ScopeEstimate.M)
        subtask = Subtask(id="st_001", title="Make it", action_budget=10, actions_used=7)

        _, user = assemble_context(goal, subtask, {}, [])
        assert "WARNING" in user
        assert "running low" in user.lower()

    def test_critical_at_85_percent(self):
        from agents.maya_code.context_window import assemble_context
        from agents.maya_code.contracts import ParsedGoal, Subtask, ScopeEstimate

        goal = ParsedGoal(raw="Build app", scope=ScopeEstimate.M)
        subtask = Subtask(id="st_001", title="Make it", action_budget=10, actions_used=9)

        _, user = assemble_context(goal, subtask, {}, [])
        assert "CRITICAL" in user
        assert "done" in user.lower()

    def test_no_warning_at_50_percent(self):
        from agents.maya_code.context_window import assemble_context
        from agents.maya_code.contracts import ParsedGoal, Subtask, ScopeEstimate

        goal = ParsedGoal(raw="Build app", scope=ScopeEstimate.M)
        subtask = Subtask(id="st_001", title="Make it", action_budget=10, actions_used=5)

        _, user = assemble_context(goal, subtask, {}, [])
        assert "WARNING" not in user
        assert "CRITICAL" not in user


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
