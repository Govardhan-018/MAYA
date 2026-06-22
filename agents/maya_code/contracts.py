"""Pydantic contracts for Maya Code Agent.

Every LLM output and every internal data structure is typed here.
Raw LLM text is always parsed into one of these before any action is taken.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Job / phase enums ─────────────────────────────────────────────────────────

class JobState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Phase(str, Enum):
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    FIXING = "FIXING"
    DONE = "DONE"


# ── Status snapshot (what get_status returns / disk mirror) ───────────────────

class StatusSnapshot(BaseModel):
    job_id: str
    state: JobState = JobState.PENDING
    phase: Phase = Phase.ANALYZING
    goal: str = ""
    progress: float = 0.0
    current_step: str = ""
    step_index: int = 0
    total_steps: int = 0
    log_tail: list[str] = Field(default_factory=list)
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    done: bool = False
    summary: Optional[str] = None
    error: Optional[str] = None
    dry_run: bool = False
    # v2 fields (optional, backward-compatible)
    version: str = "v1"
    subtasks: Optional[list[dict]] = None
    current_subtask: Optional[str] = None
    subtask_index: int = 0
    total_subtasks: int = 0


# ── Project analysis result ───────────────────────────────────────────────────

class ProjectAnalysis(BaseModel):
    project_type: str = "unknown"
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    build_tool: Optional[str] = None
    test_runner: Optional[str] = None
    test_command: Optional[str] = None
    entry_points: list[str] = Field(default_factory=list)
    file_tree: list[str] = Field(default_factory=list)
    dependency_files: list[str] = Field(default_factory=list)
    notes: str = ""


# ── Plan step (frozen after planning) ────────────────────────────────────────

class StepAction(str, Enum):
    CREATE_FILE = "create_file"
    MODIFY_FILE = "modify_file"
    DELETE_FILE = "delete_file"
    RUN_COMMAND = "run_command"
    INSTALL_DEPS = "install_deps"
    RUN_TESTS = "run_tests"


class PlanStep(BaseModel):
    id: int
    description: str
    action: StepAction
    target: str = ""
    content: Optional[str] = None
    command: Optional[str] = None
    expected_outcome: str = ""
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class CodingPlan(BaseModel):
    goal: str
    summary: str
    steps: list[PlanStep]
    test_strategy: str = ""


# ── LLM structured outputs ───────────────────────────────────────────────────

class LLMPlanResponse(BaseModel):
    """Schema the planner LLM must produce."""
    goal: str
    summary: str
    steps: list[PlanStep]
    test_strategy: str = ""


class LLMFixResponse(BaseModel):
    """Schema the fixer LLM must produce."""
    diagnosis: str
    fix_action: StepAction
    target: str = ""
    content: Optional[str] = None
    command: Optional[str] = None
    expected_outcome: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class LLMAnalysisResponse(BaseModel):
    """Schema the analyzer LLM must produce."""
    project_type: str = "unknown"
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    build_tool: Optional[str] = None
    test_runner: Optional[str] = None
    test_command: Optional[str] = None
    entry_points: list[str] = Field(default_factory=list)
    notes: str = ""


# ── Step execution result ─────────────────────────────────────────────────────

class StepResult(BaseModel):
    step_id: int
    success: bool
    action: StepAction
    target: str = ""
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    rolled_back: bool = False


# ── Completion report ─────────────────────────────────────────────────────────

class CompletionReport(BaseModel):
    job_id: str
    goal: str
    state: JobState
    total_steps: int = 0
    steps_completed: int = 0
    steps_failed: int = 0
    fixes_applied: int = 0
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)
    test_results: Optional[str] = None
    summary: str = ""
    duration_seconds: float = 0.0
    model_used: str = ""
    dry_run: bool = False


# ═════════════════════════════════════════════════════════════════════════════
#  v2 — Agentic loop types
# ═════════════════════════════════════════════════════════════════════════════

class ToolName(str, Enum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EDIT_FILE = "edit_file"
    RUN_CMD = "run_cmd"
    SEARCH_CODE = "search_code"
    LIST_FILES = "list_files"
    RUN_TESTS = "run_tests"
    DONE = "done"


class ToolCall(BaseModel):
    tool: ToolName
    args: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""


class ToolResult(BaseModel):
    tool: ToolName
    success: bool
    output: str = ""
    error: Optional[str] = None


class ActionRecord(BaseModel):
    iteration: int
    tool_call: ToolCall
    tool_result: ToolResult
    timestamp: str = ""


# ── Scope estimation ─────────────────────────────────────────────────────────

class ScopeEstimate(str, Enum):
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


class ParsedGoal(BaseModel):
    raw: str
    refined: str = ""
    scope: ScopeEstimate = ScopeEstimate.M
    key_files: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class LLMGoalParseResponse(BaseModel):
    refined: str
    scope: str = "M"
    key_files: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


# ── Subtask DAG ──────────────────────────────────────────────────────────────

class SubtaskState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class Subtask(BaseModel):
    id: str
    title: str
    description: str = ""
    depends_on: list[str] = Field(default_factory=list)
    state: SubtaskState = SubtaskState.PENDING
    action_budget: int = 30
    actions_used: int = 0
    relevant_files: list[str] = Field(default_factory=list)
    action_history: list[ActionRecord] = Field(default_factory=list)
    error: Optional[str] = None
    summary: Optional[str] = None


class SubtaskGraph(BaseModel):
    goal: str
    subtasks: list[Subtask]
    execution_order: list[str] = Field(default_factory=list)


class LLMDecompositionResponse(BaseModel):
    subtasks: list[dict[str, Any]] = Field(default_factory=list)
