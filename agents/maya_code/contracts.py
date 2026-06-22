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
