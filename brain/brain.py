"""Brain — the central orchestrator of the MAYA AI assistant.

Flow:
    command  →  Memory(context)  →  Planner  →  WorkQueue  →  Executor
            →  Memory(record)   →  ResponseGenerator  →  text

Usage:
    from brain import Brain

    brain = Brain()
    response = brain.process("Check my unread emails")
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Optional

from brain.agent_loader import AgentLoader
from brain.agent_registry_manager import AgentRegistryManager
from brain.executor import AgentExecutor
from brain.planner import Planner
from brain.queue_manager import WorkQueue
from brain.response_generator import ResponseGenerator
from brain.schemas.plan_schema import ExecutionPlan, TaskResult, TaskStatus
from brain.utils.config import MAX_WORKERS, TASK_MAX_RETRIES, TASK_TIMEOUT_SECONDS
from brain.utils.logger import log_brain


class Brain:
    """Top-level MAYA Brain. Call :meth:`process` with a user command."""

    def __init__(
        self,
        *,
        max_workers: int = MAX_WORKERS,
        task_timeout: int = TASK_TIMEOUT_SECONDS,
        max_retries: int = TASK_MAX_RETRIES,
        preload_agents: bool = False,
        enable_memory: bool = True,
    ) -> None:
        self._registry = AgentRegistryManager()
        self._registry.load()

        self._loader = AgentLoader(self._registry)
        self._planner = Planner(self._registry)
        self._executor = AgentExecutor(
            self._registry,
            self._loader,
            max_workers=max_workers,
            task_timeout=task_timeout,
            max_retries=max_retries,
        )
        self._response_gen = ResponseGenerator()

        self._memory: Optional[Any] = None
        if enable_memory:
            from memory.memory_manager import MemoryManager
            self._memory = MemoryManager()
            recovery_info = self._memory.startup()
            log_brain("memory_initialized", recovery=recovery_info)

        if preload_agents:
            load_results = self._loader.preload_all()
            loaded = sum(1 for v in load_results.values() if v is None)
            failed = sum(1 for v in load_results.values() if v is not None)
            log_brain("agents_preloaded", loaded=loaded, failed=failed)

        log_brain(
            "brain_initialized",
            agents=self._registry.list_agents(),
            max_workers=max_workers,
            task_timeout=task_timeout,
            max_retries=max_retries,
            memory_enabled=enable_memory,
        )

    def process(
        self,
        command: str,
        conversation_context: Optional[str] = None,
    ) -> str:
        """Process a user voice command end-to-end and return a spoken response.

        This is the single entry point the voice layer calls.
        """
        request_start = time.perf_counter()
        log_brain("request_start", command=command)

        try:
            # Record user message and build memory context
            if self._memory:
                self._memory.add_user_message(command)
                if conversation_context is None:
                    conversation_context = self._memory.get_context_for_planner(command)

            plan = self._planner.plan(command, conversation_context)

            if not plan.requires_agents:
                response = self._response_gen.generate_direct(
                    command, plan.direct_response, conversation_context
                )
                duration_ms = (time.perf_counter() - request_start) * 1000

                if self._memory:
                    self._memory.add_assistant_message(response)
                    self._memory.record_planner_execution(
                        command, plan.model_dump(), [], response, duration_ms,
                    )
                    self._memory.save_state()

                log_brain(
                    "request_complete",
                    path="direct",
                    duration_ms=round(duration_ms, 2),
                )
                return response

            queue = WorkQueue()
            results = self._executor.execute_plan(plan, queue)

            # Record agent executions in memory
            if self._memory:
                for r in results:
                    summary = ""
                    if r.output and isinstance(r.output, dict):
                        summary = r.output.get("message", str(r.output)[:200])
                    self._memory.record_agent_execution(
                        agent=r.agent,
                        action=r.action,
                        parameters={},
                        status=r.status.value,
                        result_summary=summary,
                        duration_ms=r.duration_ms,
                    )

            response = self._response_gen.generate(
                command, results, conversation_context
            )

            duration_ms = (time.perf_counter() - request_start) * 1000

            if self._memory:
                self._memory.add_assistant_message(response)
                self._memory.record_planner_execution(
                    command,
                    plan.model_dump(),
                    [r.model_dump() for r in results],
                    response,
                    duration_ms,
                )
                self._memory.save_state()

            log_brain(
                "request_complete",
                path="agent",
                task_count=len(results),
                summary=queue.get_status_summary(),
                duration_ms=round(duration_ms, 2),
            )
            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - request_start) * 1000
            log_brain(
                "request_error",
                command=command,
                error=str(exc),
                traceback=traceback.format_exc(),
                duration_ms=round(duration_ms, 2),
            )
            return (
                "I ran into a problem processing your request. "
                "Could you try again?"
            )

    def process_raw(
        self,
        command: str,
        conversation_context: Optional[str] = None,
    ) -> dict[str, Any]:
        """Process a command and return structured output (for debugging/tests).

        Returns a dict with plan, results, response, and timing.
        """
        request_start = time.perf_counter()

        try:
            if self._memory:
                self._memory.add_user_message(command)
                if conversation_context is None:
                    conversation_context = self._memory.get_context_for_planner(command)

            plan = self._planner.plan(command, conversation_context)

            if not plan.requires_agents:
                response = self._response_gen.generate_direct(
                    command, plan.direct_response, conversation_context
                )
                if self._memory:
                    self._memory.add_assistant_message(response)
                return {
                    "status": "success",
                    "path": "direct",
                    "plan": plan.model_dump(),
                    "results": [],
                    "response": response,
                    "duration_ms": round(
                        (time.perf_counter() - request_start) * 1000, 2
                    ),
                }

            queue = WorkQueue()
            results = self._executor.execute_plan(plan, queue)

            response = self._response_gen.generate(
                command, results, conversation_context
            )

            if self._memory:
                self._memory.add_assistant_message(response)

            return {
                "status": "success",
                "path": "agent",
                "plan": plan.model_dump(),
                "results": [r.model_dump() for r in results],
                "response": response,
                "summary": queue.get_status_summary(),
                "duration_ms": round(
                    (time.perf_counter() - request_start) * 1000, 2
                ),
            }

        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "duration_ms": round(
                    (time.perf_counter() - request_start) * 1000, 2
                ),
            }

    # ── utility methods ────────────────────────────────────────────────────

    def reload_registry(self) -> None:
        """Re-read registry files (call after build_registry.py)."""
        self._registry.reload()
        self._loader.clear_cache()
        log_brain("registry_reloaded")

    def list_agents(self) -> list[str]:
        return self._registry.list_agents()

    def list_actions(self, agent_name: str) -> list[str]:
        return self._registry.list_actions(agent_name)

    @property
    def registry(self) -> AgentRegistryManager:
        return self._registry

    @property
    def planner(self) -> Planner:
        return self._planner

    @property
    def executor(self) -> AgentExecutor:
        return self._executor

    @property
    def response_generator(self) -> ResponseGenerator:
        return self._response_gen

    @property
    def memory(self) -> Optional[MemoryManager]:
        return self._memory
