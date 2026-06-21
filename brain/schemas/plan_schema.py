"""Pydantic models for execution plans and task results."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanTask(BaseModel):
    """A single task within an execution plan."""

    id: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    """The full plan output by the planner LLM."""

    requires_agents: bool = True
    parallel: bool = False
    tasks: list[PlanTask] = Field(default_factory=list)
    direct_response: Optional[str] = None

    @model_validator(mode="after")
    def _validate_plan(self) -> "ExecutionPlan":
        if self.requires_agents and not self.tasks:
            raise ValueError("requires_agents=true but no tasks provided")

        task_ids = {t.id for t in self.tasks}
        for task in self.tasks:
            for dep in task.depends_on:
                if dep not in task_ids:
                    raise ValueError(
                        f"Task '{task.id}' depends on unknown task '{dep}'"
                    )
            if task.id in task.depends_on:
                raise ValueError(f"Task '{task.id}' depends on itself")

        return self


class TaskResult(BaseModel):
    """Result of executing a single task."""

    task_id: str
    agent: str
    action: str
    status: TaskStatus
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    retries_used: int = 0
