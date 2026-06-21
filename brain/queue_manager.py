"""Work queue with dependency resolution and state tracking.

Manages task lifecycle: PENDING → RUNNING → COMPLETED/FAILED/CANCELLED.
Resolves inter-task dependencies before yielding ready tasks.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from brain.schemas.plan_schema import (
    ExecutionPlan,
    PlanTask,
    TaskResult,
    TaskStatus,
)
from brain.utils.logger import log_brain


class WorkQueue:
    """Thread-safe work queue with dependency-aware scheduling."""

    def __init__(self) -> None:
        self._tasks: dict[str, PlanTask] = {}
        self._status: dict[str, TaskStatus] = {}
        self._results: dict[str, TaskResult] = {}
        self._lock = threading.Lock()

    def load_plan(self, plan: ExecutionPlan) -> None:
        """Populate the queue from an execution plan."""
        with self._lock:
            self._tasks.clear()
            self._status.clear()
            self._results.clear()
            for task in plan.tasks:
                self._tasks[task.id] = task
                self._status[task.id] = TaskStatus.PENDING

        log_brain("queue_loaded", task_count=len(plan.tasks))

    def get_ready_tasks(self) -> list[PlanTask]:
        """Return all PENDING tasks whose dependencies are COMPLETED."""
        with self._lock:
            return self._get_ready_tasks_unlocked()

    def _get_ready_tasks_unlocked(self) -> list[PlanTask]:
        ready: list[PlanTask] = []
        for task_id, task in self._tasks.items():
            if self._status[task_id] != TaskStatus.PENDING:
                continue
            deps_met = all(
                self._status.get(dep) == TaskStatus.COMPLETED
                for dep in task.depends_on
            )
            if deps_met:
                ready.append(task)
        return ready

    def mark_running(self, task_id: str) -> None:
        with self._lock:
            self._status[task_id] = TaskStatus.RUNNING

    def mark_completed(self, task_id: str, result: TaskResult) -> None:
        with self._lock:
            self._status[task_id] = TaskStatus.COMPLETED
            self._results[task_id] = result

    def mark_failed(self, task_id: str, result: TaskResult) -> None:
        with self._lock:
            self._status[task_id] = TaskStatus.FAILED
            self._results[task_id] = result
            self._cancel_dependents(task_id)

    def _cancel_dependents(self, failed_id: str) -> None:
        """Cancel all tasks that transitively depend on a failed task."""
        for task_id, task in self._tasks.items():
            if self._status[task_id] != TaskStatus.PENDING:
                continue
            if failed_id in task.depends_on:
                self._status[task_id] = TaskStatus.CANCELLED
                self._results[task_id] = TaskResult(
                    task_id=task_id,
                    agent=task.agent,
                    action=task.action,
                    status=TaskStatus.CANCELLED,
                    error=f"Cancelled: dependency '{failed_id}' failed",
                )
                log_brain("task_cancelled", task_id=task_id, reason=failed_id)
                self._cancel_dependents(task_id)

    def is_complete(self) -> bool:
        """True when no tasks are PENDING or RUNNING."""
        with self._lock:
            return all(
                s in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
                for s in self._status.values()
            )

    def has_blocked_tasks(self) -> bool:
        """True when there are PENDING tasks but none are ready (deadlock)."""
        with self._lock:
            has_pending = any(
                s == TaskStatus.PENDING for s in self._status.values()
            )
            if not has_pending:
                return False
            ready = self._get_ready_tasks_unlocked()
            return len(ready) == 0

    def get_all_results(self) -> list[TaskResult]:
        with self._lock:
            return list(self._results.values())

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        with self._lock:
            return self._results.get(task_id)

    def get_status_summary(self) -> dict[str, int]:
        with self._lock:
            summary: dict[str, int] = {}
            for status in self._status.values():
                summary[status.value] = summary.get(status.value, 0) + 1
            return summary

    @property
    def task_count(self) -> int:
        return len(self._tasks)
