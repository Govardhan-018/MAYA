"""v2 Agentic Loop — READ → THINK → ACT → OBSERVE per subtask.

The LLM picks one tool per iteration, sees the result, and decides the next
action.  Stops on: DONE tool, budget exhaustion, cancellation, or consecutive
failure limit.
"""

from __future__ import annotations

import time
import traceback
from typing import Callable, Optional

from agents.maya_code import config
from agents.maya_code.context_window import assemble_context
from agents.maya_code.contracts import (
    ActionRecord,
    ParsedGoal,
    Subtask,
    SubtaskState,
    ToolCall,
    ToolName,
    ToolResult,
)
from agents.maya_code.models import LLMError, call_llm_structured
from agents.maya_code.tool_executor import ToolBelt


def run_subtask(
    subtask: Subtask,
    parsed_goal: ParsedGoal,
    analysis_text: str,
    tool_belt: ToolBelt,
    log_fn: Callable[[str], None],
    cancel_check: Callable[[], bool],
    force_done_at_budget: bool = True,
) -> Subtask:
    """Execute one subtask through the agentic loop.

    Returns the updated subtask with final state, action history, and summary.
    Never raises — all errors are captured in subtask.state / subtask.error.
    """
    subtask.state = SubtaskState.RUNNING
    consecutive_failures = 0
    consecutive_same_file_edits = 0
    last_edit_path = ""
    log_fn(f"Starting subtask: {subtask.title}")

    try:
        while subtask.actions_used < subtask.action_budget:
            if cancel_check():
                subtask.state = SubtaskState.FAILED
                subtask.error = "Cancelled by user"
                log_fn("  Subtask cancelled")
                return subtask

            # ── THINK: assemble context and ask LLM ─────────────────────
            system_prompt, user_prompt = assemble_context(
                parsed_goal=parsed_goal,
                subtask=subtask,
                file_cache=tool_belt.file_cache,
                action_history=subtask.action_history,
                analysis_text=analysis_text,
            )

            try:
                tool_call, model_used = call_llm_structured(
                    system_prompt, user_prompt, ToolCall
                )
            except LLMError as exc:
                consecutive_failures += 1
                log_fn(f"  LLM error (attempt {consecutive_failures}): {exc}")
                if consecutive_failures >= config.V2_CONSECUTIVE_FAILURE_LIMIT:
                    subtask.state = SubtaskState.FAILED
                    subtask.error = f"LLM failed {consecutive_failures} times consecutively"
                    log_fn(f"  Subtask failed: {subtask.error}")
                    return subtask
                continue

            # ── Detect edit loop (same file edited 4+ times in a row) ──
            if tool_call.tool == ToolName.EDIT_FILE:
                edit_path = tool_call.args.get("path", "")
                if edit_path == last_edit_path:
                    consecutive_same_file_edits += 1
                else:
                    consecutive_same_file_edits = 1
                    last_edit_path = edit_path

                if consecutive_same_file_edits >= 4:
                    log_fn(f"  Edit loop detected ({consecutive_same_file_edits}x on {edit_path}) — forcing done")
                    subtask.state = SubtaskState.COMPLETED
                    subtask.summary = f"Auto-completed: edit loop detected on {edit_path}"
                    return subtask
            else:
                consecutive_same_file_edits = 0
                last_edit_path = ""

            iteration = subtask.actions_used + 1
            log_fn(f"  [{iteration}/{subtask.action_budget}] {tool_call.tool.value} — {tool_call.reasoning[:80]}")

            # ── Check for DONE signal ───────────────────────────────────
            if tool_call.tool == ToolName.DONE:
                summary = tool_call.args.get("summary", "Subtask completed")
                subtask.state = SubtaskState.COMPLETED
                subtask.summary = summary
                subtask.actions_used = iteration

                record = ActionRecord(
                    iteration=iteration,
                    tool_call=tool_call,
                    tool_result=ToolResult(tool=ToolName.DONE, success=True, output=summary),
                    timestamp=_now(),
                )
                subtask.action_history.append(record)
                log_fn(f"  Subtask completed: {summary[:100]}")
                return subtask

            # ── ACT: execute the tool ───────────────────────────────────
            tool_result = tool_belt.execute(tool_call)
            subtask.actions_used = iteration

            # ── OBSERVE: record the result ──────────────────────────────
            record = ActionRecord(
                iteration=iteration,
                tool_call=tool_call,
                tool_result=tool_result,
                timestamp=_now(),
            )
            subtask.action_history.append(record)

            if tool_result.success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                log_fn(f"  FAILED: {tool_result.error or 'unknown error'}")
                if consecutive_failures >= config.V2_CONSECUTIVE_FAILURE_LIMIT:
                    subtask.state = SubtaskState.FAILED
                    subtask.error = f"Circuit breaker: {consecutive_failures} consecutive failures"
                    log_fn(f"  Subtask failed: {subtask.error}")
                    return subtask

        # Budget exhausted — check if meaningful work was done
        made_progress = bool(tool_belt.files_created or tool_belt.files_modified)

        if force_done_at_budget and made_progress:
            subtask.state = SubtaskState.COMPLETED
            subtask.summary = (
                f"Budget exhausted after {subtask.action_budget} actions — "
                f"partial completion (created: {len(tool_belt.files_created)}, "
                f"modified: {len(tool_belt.files_modified)})"
            )
            log_fn(f"  Budget exhausted but progress made — marking as partial completion")
        else:
            subtask.state = SubtaskState.FAILED
            subtask.error = f"Action budget exhausted ({subtask.action_budget} actions)"
            log_fn(f"  Subtask failed: {subtask.error}")
        return subtask

    except Exception as exc:
        tb = traceback.format_exc()
        subtask.state = SubtaskState.FAILED
        subtask.error = f"Unexpected error: {exc}"
        log_fn(f"  FATAL: {tb[-300:]}")
        return subtask


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
