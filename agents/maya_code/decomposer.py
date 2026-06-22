"""v2 Decomposer — breaks a goal into a subtask DAG via LLM.

Produces a ``SubtaskGraph`` with dependencies, topological ordering, and
per-subtask action budgets.  Includes cycle detection via Kahn's algorithm.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from agents.maya_code import config
from agents.maya_code.contracts import (
    LLMDecompositionResponse,
    ParsedGoal,
    ScopeEstimate,
    Subtask,
    SubtaskGraph,
    SubtaskState,
)
from agents.maya_code.models import LLMError, call_llm_structured


_DECOMPOSER_SYSTEM = """\
Break a coding goal into 2-10 subtasks. Respond with ONLY JSON:

{"subtasks": [
  {"id": "st_001", "title": "Create base HTML", "description": "Create index.html with page structure, head, body, and script tags", "depends_on": [], "scope": "S", "relevant_files": ["index.html"]},
  {"id": "st_002", "title": "Add CSS styles", "description": "Create styles.css with layout, colors, responsive design", "depends_on": [], "scope": "M", "relevant_files": ["styles.css"]},
  {"id": "st_003", "title": "Core JS logic", "description": "Create app.js with main game/app logic", "depends_on": ["st_001"], "scope": "M", "relevant_files": ["app.js"]}
]}

Rules:
- IDs: "st_001", "st_002", etc.
- scope: "S" (1-2 files), "M" (3-5 files), "L" (5+ files)
- depends_on: ONLY if a subtask literally cannot start without another. Most should be [].
- NEVER make a linear chain (st_002 depends on st_001, st_003 depends on st_002, etc.)
- Keep subtasks INDEPENDENT. Creating separate files = no dependency needed.
- description: be specific — name files to create and what goes in them.
"""


def decompose(
    parsed_goal: ParsedGoal,
    analysis_text: str,
    deep_context: str,
) -> SubtaskGraph:
    """Break a goal into a ``SubtaskGraph`` with topological ordering."""
    user_prompt = (
        f"## Goal\n{parsed_goal.refined or parsed_goal.raw}\n\n"
        f"## Scope Estimate: {parsed_goal.scope.value}\n\n"
        f"## Acceptance Criteria\n"
        + "\n".join(f"- {c}" for c in parsed_goal.acceptance_criteria)
        + f"\n\n{analysis_text}\n\n{deep_context}"
    )

    try:
        resp, _ = call_llm_structured(
            _DECOMPOSER_SYSTEM, user_prompt, LLMDecompositionResponse
        )
        raw_subtasks = resp.subtasks[: config.V2_MAX_SUBTASKS]
    except LLMError:
        return _single_subtask_fallback(parsed_goal)

    if not raw_subtasks:
        return _single_subtask_fallback(parsed_goal)

    subtasks = _parse_subtasks(raw_subtasks)
    valid_ids = {st.id for st in subtasks}
    for st in subtasks:
        st.depends_on = [d for d in st.depends_on if d in valid_ids]

    order = _topological_sort(subtasks)
    if order is None:
        for st in subtasks:
            st.depends_on = []
        order = [st.id for st in subtasks]

    return SubtaskGraph(
        goal=parsed_goal.refined or parsed_goal.raw,
        subtasks=subtasks,
        execution_order=order,
    )


def _parse_subtasks(raw: list[dict[str, Any]]) -> list[Subtask]:
    """Convert raw LLM dicts into validated Subtask models."""
    result: list[Subtask] = []
    for i, item in enumerate(raw):
        st_id = str(item.get("id", f"st_{i + 1:03d}"))
        scope_str = str(item.get("scope", "M")).upper()
        budget = config.SCOPE_BUDGET_MAP.get(scope_str, config.V2_MAX_ACTIONS_M)

        result.append(Subtask(
            id=st_id,
            title=str(item.get("title", f"Subtask {i + 1}")),
            description=str(item.get("description", "")),
            depends_on=list(item.get("depends_on", [])),
            state=SubtaskState.PENDING,
            action_budget=budget,
            relevant_files=list(item.get("relevant_files", [])),
        ))
    return result


def _topological_sort(subtasks: list[Subtask]) -> list[str] | None:
    """Kahn's algorithm. Returns ordered IDs or None if cycle detected."""
    id_set = {st.id for st in subtasks}
    in_degree: dict[str, int] = {st.id: 0 for st in subtasks}
    adj: dict[str, list[str]] = {st.id: [] for st in subtasks}

    for st in subtasks:
        for dep in st.depends_on:
            if dep in id_set:
                adj[dep].append(st.id)
                in_degree[st.id] += 1

    queue: deque[str] = deque(sid for sid, deg in in_degree.items() if deg == 0)
    order: list[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(subtasks):
        return None
    return order


def _single_subtask_fallback(parsed_goal: ParsedGoal) -> SubtaskGraph:
    """Fallback: wrap the entire goal as one subtask."""
    scope = parsed_goal.scope.value
    budget = config.SCOPE_BUDGET_MAP.get(scope, config.V2_MAX_ACTIONS_M)

    st = Subtask(
        id="st_001",
        title=parsed_goal.refined or parsed_goal.raw,
        description=parsed_goal.refined or parsed_goal.raw,
        action_budget=budget,
        relevant_files=parsed_goal.key_files[:10],
    )
    return SubtaskGraph(
        goal=parsed_goal.refined or parsed_goal.raw,
        subtasks=[st],
        execution_order=["st_001"],
    )
