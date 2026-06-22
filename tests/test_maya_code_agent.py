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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
