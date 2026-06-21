"""Agent executor — runs tasks with timeouts, retries, and result capture.

Supports both parallel (ThreadPoolExecutor) and sequential execution.
Each task is isolated: a failure never crashes the executor.
"""

from __future__ import annotations

import concurrent.futures
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import Any, Optional

from brain.agent_loader import AgentLoader
from brain.agent_registry_manager import AgentRegistryManager
from brain.queue_manager import WorkQueue
from brain.schemas.plan_schema import (
    ExecutionPlan,
    PlanTask,
    TaskResult,
    TaskStatus,
)
from brain.utils.config import MAX_WORKERS, TASK_MAX_RETRIES, TASK_TIMEOUT_SECONDS
from brain.utils.logger import log_agent_call, log_brain


class AgentExecutor:
    """Executes tasks from a WorkQueue, respecting dependencies and parallelism."""

    def __init__(
        self,
        registry: AgentRegistryManager,
        loader: AgentLoader,
        *,
        max_workers: int = MAX_WORKERS,
        task_timeout: int = TASK_TIMEOUT_SECONDS,
        max_retries: int = TASK_MAX_RETRIES,
    ) -> None:
        self._registry = registry
        self._loader = loader
        self._max_workers = max_workers
        self._task_timeout = task_timeout
        self._max_retries = max_retries

    def execute_plan(self, plan: ExecutionPlan, queue: WorkQueue) -> list[TaskResult]:
        """Run every task in *plan* via *queue*, returning all results."""
        queue.load_plan(plan)

        if plan.parallel:
            self._run_parallel(queue)
        else:
            self._run_sequential(queue)

        results = queue.get_all_results()
        log_brain(
            "execution_complete",
            summary=queue.get_status_summary(),
            total_tasks=queue.task_count,
        )
        return results

    # ── execution modes ────────────────────────────────────────────────────

    def _run_sequential(self, queue: WorkQueue) -> None:
        """Execute tasks one at a time, respecting dependency order.

        Uses a single-thread pool to enforce per-task timeouts without
        spawning a new pool per call.
        """
        with ThreadPoolExecutor(max_workers=1) as timeout_pool:
            while not queue.is_complete():
                ready = queue.get_ready_tasks()
                if not ready:
                    if queue.has_blocked_tasks():
                        log_brain("deadlock_detected")
                    break

                for task in ready:
                    result = self._execute_single(task, queue, timeout_pool)
                    if result.status == TaskStatus.COMPLETED:
                        queue.mark_completed(task.id, result)
                    else:
                        queue.mark_failed(task.id, result)

    def _run_parallel(self, queue: WorkQueue) -> None:
        """Execute independent tasks concurrently via ThreadPoolExecutor."""
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            while not queue.is_complete():
                ready = queue.get_ready_tasks()
                if not ready:
                    if queue.has_blocked_tasks():
                        log_brain("deadlock_detected")
                    break

                futures: dict[Future[TaskResult], PlanTask] = {}
                for task in ready:
                    future = pool.submit(self._execute_single, task, queue, None)
                    futures[future] = task

                for future in as_completed(futures):
                    task = futures[future]
                    try:
                        result = future.result(timeout=self._task_timeout + 5)
                    except Exception as exc:
                        result = TaskResult(
                            task_id=task.id,
                            agent=task.agent,
                            action=task.action,
                            status=TaskStatus.FAILED,
                            error=f"Future error: {exc}",
                        )

                    if result.status == TaskStatus.COMPLETED:
                        queue.mark_completed(task.id, result)
                    else:
                        queue.mark_failed(task.id, result)

    # ── single-task execution with retries ─────────────────────────────────

    def _execute_single(
        self,
        task: PlanTask,
        queue: WorkQueue,
        timeout_pool: Optional[ThreadPoolExecutor] = None,
    ) -> TaskResult:
        """Execute one task with retry logic.

        If *timeout_pool* is provided, agent calls are submitted to it with a
        timeout.  Otherwise the call runs inline (the caller is responsible
        for timeout — e.g. ``_run_parallel`` uses ``future.result(timeout=...)``).
        """
        queue.mark_running(task.id)
        last_error: str = ""
        start = time.perf_counter()

        for attempt in range(self._max_retries + 1):
            log_agent_call(
                "task_start",
                task_id=task.id,
                agent=task.agent,
                action=task.action,
                attempt=attempt,
            )

            start = time.perf_counter()
            try:
                if timeout_pool is not None:
                    future = timeout_pool.submit(self._call_agent, task)
                    try:
                        output = future.result(timeout=self._task_timeout)
                    except concurrent.futures.TimeoutError:
                        raise TimeoutError(
                            f"{task.agent}.{task.action} exceeded {self._task_timeout}s"
                        )
                else:
                    output = self._call_agent(task)
                duration_ms = (time.perf_counter() - start) * 1000

                status = self._determine_status(output)

                if status == TaskStatus.COMPLETED:
                    result = TaskResult(
                        task_id=task.id,
                        agent=task.agent,
                        action=task.action,
                        status=TaskStatus.COMPLETED,
                        output=output,
                        duration_ms=duration_ms,
                        retries_used=attempt,
                    )
                    log_agent_call(
                        "task_success",
                        task_id=task.id,
                        duration_ms=round(duration_ms, 2),
                        attempt=attempt,
                    )
                    return result

                last_error = output.get("message", "Agent returned error status")
                log_agent_call(
                    "task_agent_error",
                    task_id=task.id,
                    attempt=attempt,
                    error=last_error,
                )

            except TimeoutError:
                duration_ms = (time.perf_counter() - start) * 1000
                last_error = f"Task timed out after {self._task_timeout}s"
                log_agent_call(
                    "task_timeout",
                    task_id=task.id,
                    attempt=attempt,
                    timeout=self._task_timeout,
                )

            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                last_error = str(exc)
                log_agent_call(
                    "task_exception",
                    task_id=task.id,
                    attempt=attempt,
                    error=last_error,
                    traceback=traceback.format_exc(),
                )

        result = TaskResult(
            task_id=task.id,
            agent=task.agent,
            action=task.action,
            status=TaskStatus.FAILED,
            error=last_error,
            duration_ms=(time.perf_counter() - start) * 1000,
            retries_used=self._max_retries,
        )
        log_agent_call("task_failed_final", task_id=task.id, error=last_error)
        return result

    def _call_agent(self, task: PlanTask) -> dict[str, Any]:
        """Build the request JSON and call the agent's execute function.

        Timeout is enforced by the caller (_run_parallel uses future.result(timeout=...)
        and _run_sequential wraps the call in a single shared timeout pool).
        """
        execute_fn = self._loader.get_execute_fn(task.agent)

        request = {
            "action": task.action,
            "parameters": task.parameters,
        }

        return execute_fn(request)

    def _determine_status(self, output: dict[str, Any]) -> TaskStatus:
        """Check the agent's output dict for success/error status."""
        status_field = output.get("status", "")
        if status_field == "success":
            return TaskStatus.COMPLETED
        if status_field == "error":
            return TaskStatus.FAILED
        return TaskStatus.COMPLETED
