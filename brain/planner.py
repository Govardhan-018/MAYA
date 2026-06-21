"""LLM-based planner — converts user commands into validated execution plans.

Flow:
    1. Build a prompt with the user command + registry context.
    2. Call the planner LLM (Ollama).
    3. Parse and validate the JSON plan via Pydantic.
    4. Validate agents/actions/params against the registry.
    5. On failure: retry (up to PLANNER_MAX_RETRIES), then local fallback.
"""

from __future__ import annotations

import json
import re
import textwrap
import traceback
from typing import Any, Optional

import ollama

from brain.agent_registry_manager import AgentRegistryManager
from brain.schemas.plan_schema import ExecutionPlan, PlanTask
from brain.utils.config import (
    OLLAMA_BASE_URL,
    PLANNER_LOCAL_FALLBACK,
    PLANNER_MAX_RETRIES,
    PLANNER_MODEL,
    PLANNER_NUM_CTX,
    PLANNER_TEMPERATURE,
)
from brain.utils.logger import log_planner


_SYSTEM_PROMPT = textwrap.dedent("""\
You are the MAYA AI planner. Your job is to convert a user command into a
JSON execution plan.

RULES — follow exactly:
1. Output ONLY valid JSON. No markdown fences, no explanation, no commentary.
2. If the command can be answered without any agent (greetings, general
   knowledge, opinions, conversation), return:
   {"requires_agents": false, "tasks": [], "direct_response": "<your answer>"}
3. If agents are needed, return:
   {"requires_agents": true, "parallel": <true|false>, "tasks": [...]}
4. Each task must have: "id", "agent", "action", "parameters".
5. Use ONLY agents and actions from the AGENT REGISTRY below.
6. If a task depends on another task's output, add "depends_on": ["task_id"].
7. Set "parallel": true only when tasks are independent.
8. Task IDs must be unique strings like "task_1", "task_2", etc.
9. Parameters must satisfy the required_params for each action.
10. Do NOT invent agents or actions that are not in the registry.
""")


def _build_prompt(
    command: str,
    registry_context: str,
    conversation_context: Optional[str] = None,
) -> str:
    """Assemble the user-facing prompt sent to the planner LLM."""
    parts: list[str] = []

    parts.append("AGENT REGISTRY:\n")
    parts.append(registry_context)
    parts.append("\n")

    if conversation_context:
        parts.append("RECENT CONVERSATION:\n")
        parts.append(conversation_context)
        parts.append("\n")

    parts.append(f"USER COMMAND: {command}\n")
    parts.append("Respond with JSON only.")

    return "\n".join(parts)


def _extract_json(raw: str) -> str:
    """Pull a JSON object from LLM output that may include markdown fences."""
    raw = raw.strip()

    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    start = raw.find("{")
    if start == -1:
        return raw

    decoder = json.JSONDecoder()
    try:
        _, end_idx = decoder.raw_decode(raw, start)
        return raw[start:end_idx]
    except (json.JSONDecodeError, ValueError):
        pass

    depth = 0
    end = start
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return raw[start:end]


def _call_ollama(
    prompt: str,
    model: str,
    *,
    temperature: float = PLANNER_TEMPERATURE,
    num_ctx: int = PLANNER_NUM_CTX,
) -> str:
    """Send a chat request to Ollama and return the assistant content.

    Requests JSON format from Ollama so the model is constrained to
    produce valid JSON, reducing parse failures with smaller models.
    """
    client = ollama.Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        format="json",
        options={"temperature": temperature, "num_ctx": num_ctx},
    )
    return response.message.content or ""


class Planner:
    """Converts user commands into validated ExecutionPlans."""

    def __init__(self, registry: AgentRegistryManager) -> None:
        self._registry = registry

    def plan(
        self,
        command: str,
        conversation_context: Optional[str] = None,
    ) -> ExecutionPlan:
        """Generate an execution plan for *command*.

        Tries the primary model up to PLANNER_MAX_RETRIES + 1 times, then
        falls back to the local model with the same retry budget.
        """
        registry_context = self._registry.get_planner_context_compact()
        prompt = _build_prompt(command, registry_context, conversation_context)

        log_planner("plan_start", command=command, model=PLANNER_MODEL)

        plan = self._try_model(PLANNER_MODEL, prompt, command)
        if plan is not None:
            return plan

        if PLANNER_LOCAL_FALLBACK != PLANNER_MODEL:
            log_planner(
                "fallback_to_local",
                command=command,
                model=PLANNER_LOCAL_FALLBACK,
            )
            plan = self._try_model(PLANNER_LOCAL_FALLBACK, prompt, command)
            if plan is not None:
                return plan

        log_planner("plan_all_failed", command=command)
        return ExecutionPlan(
            requires_agents=False,
            tasks=[],
            direct_response=(
                "I'm having trouble planning right now. "
                "Could you rephrase your request?"
            ),
        )

    def _try_model(
        self, model: str, prompt: str, command: str
    ) -> Optional[ExecutionPlan]:
        """Attempt planning with *model*, returning None on exhausted retries."""
        last_error: str = ""

        for attempt in range(PLANNER_MAX_RETRIES + 1):
            try:
                raw = _call_ollama(prompt, model)
                log_planner(
                    "llm_response",
                    model=model,
                    attempt=attempt,
                    raw_length=len(raw),
                )

                json_str = _extract_json(raw)
                data = json.loads(json_str)
                plan = ExecutionPlan.model_validate(data)
                plan = self._validate_against_registry(plan)

                log_planner(
                    "plan_success",
                    model=model,
                    attempt=attempt,
                    requires_agents=plan.requires_agents,
                    task_count=len(plan.tasks),
                )
                return plan

            except Exception as exc:
                last_error = str(exc)
                log_planner(
                    "plan_attempt_failed",
                    model=model,
                    attempt=attempt,
                    error=last_error,
                    traceback=traceback.format_exc(),
                )

        return None

    def _validate_against_registry(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Check every task's agent/action/params against the live registry.

        Raises ValueError on irrecoverable issues. Attempts auto-repair for
        minor problems (missing optional params are fine).
        """
        if not plan.requires_agents:
            return plan

        errors: list[str] = []
        for task in plan.tasks:
            task_errors = self._registry.validate_task(
                task.agent, task.action, task.parameters
            )
            errors.extend(task_errors)

        if errors:
            raise ValueError(
                "Registry validation failed: " + "; ".join(errors)
            )
        return plan
