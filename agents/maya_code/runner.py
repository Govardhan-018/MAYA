"""Runner — background thread that drives the full coding loop.

v1 lifecycle: start_task() → daemon thread → ANALYZING → PLANNING →
              EXECUTING → VERIFYING → (FIXING loop) → DONE

v2 lifecycle: start_task() → daemon thread → ANALYZING → goal_parse →
              scope gate → deep_analyze → PLANNING (decompose) →
              EXECUTING (agentic loop per subtask) → DONE

Scope "S" tasks use v1 (fast path).  "M"/"L"/"XL" use v2 (agentic loop).
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Optional

from agents.maya_code import config
from agents.maya_code.analyzer import analyze_project, format_analysis_for_llm
from agents.maya_code.checkpoint import CheckpointManager
from agents.maya_code.contracts import (
    CodingPlan,
    CompletionReport,
    JobState,
    LLMFixResponse,
    LLMPlanResponse,
    Phase,
    PlanStep,
    ScopeEstimate,
    StepAction,
    StepResult,
    StatusSnapshot,
    SubtaskState,
)
from agents.maya_code.executor import StepExecutor
from agents.maya_code.job_store import JobStore
from agents.maya_code.models import LLMError, call_llm_structured, call_llm_raw
from agents.maya_code.state_machine import IllegalTransition, PhaseMachine
from agents.maya_code.validators import ValidationError, validate_project_root

# ── singleton store ───────────────────────────────────────────────────────────
_store = JobStore()


def get_store() -> JobStore:
    return _store


# ── v1 prompts ───────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """\
Create a step-by-step coding plan. Respond with ONLY JSON:

{"goal": "what to build", "summary": "brief plan summary", "steps": [
  {"id": 1, "description": "Create main file", "action": "create_file", "target": "src/app.py", "content": "full file content here", "command": null, "expected_outcome": "File created", "confidence": 0.9}
], "test_strategy": "how to verify"}

Each step needs: id (int), description, action, target (file path), content or command, expected_outcome, confidence (0-1).
Actions: create_file, modify_file, delete_file, run_command, install_deps, run_tests.
For modify_file: provide COMPLETE new file content. Keep the plan minimal.
"""

_FIXER_SYSTEM = """\
Fix a coding error. Respond with ONLY JSON:

{"diagnosis": "what went wrong", "fix_action": "create_file", "target": "src/app.py", "content": "fixed file content", "command": null, "expected_outcome": "Error resolved", "confidence": 0.8}

fix_action: create_file, modify_file, delete_file, or run_command.
For file fixes: provide COMPLETE file content. Diagnose the root cause first.
"""


# ── public API ───────────────────────────────────────────────────────────────

def start_task(
    goal: str,
    project_root: str,
    *,
    dry_run: bool = False,
    context: Optional[str] = None,
) -> dict:
    """Start a coding task in a background thread.  Returns immediately."""
    if not config.ENABLED:
        return {"status": "error", "message": "Maya Code Agent is disabled (MAYA_CODE_AGENT_ENABLED=false)"}

    try:
        root = validate_project_root(project_root)
    except ValidationError as exc:
        return {"status": "error", "message": str(exc)}

    job_id = f"code_{uuid.uuid4().hex[:12]}"
    _store.create(job_id, goal, dry_run=dry_run)

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, goal, root, dry_run, context),
        daemon=True,
        name=f"maya-code-{job_id}",
    )
    thread.start()

    return {
        "status": "success",
        "action": "start_task",
        "data": {"job_id": job_id, "message": f"Task started: {goal}"},
    }


def get_status(job_id: str) -> dict:
    snap = _store.get(job_id)
    if snap is None:
        return {"status": "error", "message": f"Unknown job: {job_id}"}
    return {"status": "success", "action": "get_status", "data": snap.model_dump()}


def cancel_task(job_id: str) -> dict:
    snap = _store.cancel(job_id)
    if snap is None:
        return {"status": "error", "message": f"Unknown job: {job_id}"}
    return {"status": "success", "action": "cancel_task", "data": {"job_id": job_id, "cancelled": True}}


def list_jobs() -> dict:
    jobs = _store.list_jobs()
    return {
        "status": "success",
        "action": "list_jobs",
        "data": {"jobs": [j.model_dump() for j in jobs]},
    }


# ── dispatcher ───────────────────────────────────────────────────────────────

def _run_job(
    job_id: str,
    goal: str,
    project_root: Path,
    dry_run: bool,
    context: Optional[str],
) -> None:
    """Dispatch to v1 or v2 based on scope estimation.  Never raises."""
    def log(msg: str) -> None:
        _store.update(job_id, log_line=msg)

    try:
        _store.update(job_id, state=JobState.RUNNING)

        # ── 1. ANALYZING (shared by v1 and v2) ──────────────────────────
        log("Analyzing project structure...")
        _store.update(job_id, phase=Phase.ANALYZING, current_step="Scanning project")
        analysis = analyze_project(project_root)
        analysis_text = format_analysis_for_llm(analysis)
        log(f"Detected: {analysis.project_type} ({', '.join(analysis.languages[:5])})")

        if _is_cancelled(job_id):
            return

        # ── 2. Scope estimation (v2 gate) ───────────────────────────────
        use_v2 = False
        parsed_goal = None

        if config.V2_ENABLED and not dry_run:
            try:
                from agents.maya_code.goal_parser import parse_goal
                log("Parsing goal and estimating scope...")
                _store.update(job_id, current_step="Estimating scope")
                parsed_goal = parse_goal(goal, analysis)
                scope_order = ["S", "M", "L", "XL"]
                threshold_idx = scope_order.index(config.V2_SCOPE_THRESHOLD) if config.V2_SCOPE_THRESHOLD in scope_order else 1
                goal_idx = scope_order.index(parsed_goal.scope.value) if parsed_goal.scope.value in scope_order else 1
                use_v2 = goal_idx >= threshold_idx
                log(f"Scope: {parsed_goal.scope.value} → {'v2 agentic' if use_v2 else 'v1 fast path'}")
            except Exception as exc:
                log(f"Scope estimation failed ({exc}), falling back to v1")

        if use_v2 and parsed_goal:
            _run_job_v2(job_id, goal, project_root, context, analysis, analysis_text, parsed_goal, log)
        else:
            _run_job_v1(job_id, goal, project_root, dry_run, context, analysis, analysis_text, log)

    except Exception as exc:
        tb = traceback.format_exc()
        _store.update(
            job_id,
            state=JobState.FAILED,
            error=f"Unexpected error: {exc}",
            log_line=f"FATAL: {tb[-500:]}",
            done=True,
        )


# ═════════════════════════════════════════════════════════════════════════════
#  v1 — single-shot plan executor (fast path for small tasks)
# ═════════════════════════════════════════════════════════════════════════════

def _run_job_v1(
    job_id: str,
    goal: str,
    project_root: Path,
    dry_run: bool,
    context: Optional[str],
    analysis,
    analysis_text: str,
    log,
) -> None:
    machine = PhaseMachine()
    checkpoint = CheckpointManager(job_id, project_root)
    model_used = ""
    start_time = time.time()

    def fail(msg: str) -> None:
        _store.update(job_id, state=JobState.FAILED, error=msg, done=True)
        machine.force_terminal(Phase.DONE)

    try:
        # ── PLANNING ─────────────────────────────────────────────────────
        machine.transition(Phase.PLANNING)
        _store.update(job_id, phase=Phase.PLANNING, current_step="Generating plan")
        log("Generating coding plan via LLM...")

        user_prompt = f"## Goal\n{goal}\n\n## Project Analysis\n{analysis_text}"
        if context:
            user_prompt += f"\n\n## Additional Context\n{context}"

        try:
            plan_resp, model_used = call_llm_structured(
                _PLANNER_SYSTEM, user_prompt, LLMPlanResponse
            )
        except LLMError as exc:
            fail(f"Planning failed: {exc}")
            return

        plan = CodingPlan(
            goal=plan_resp.goal,
            summary=plan_resp.summary,
            steps=plan_resp.steps,
            test_strategy=plan_resp.test_strategy,
        )

        if not plan.steps:
            fail("LLM produced an empty plan")
            return

        total = len(plan.steps)
        _store.update(job_id, total_steps=total,
                      log_line=f"Plan: {plan.summary} ({total} steps)")

        if dry_run:
            log("[DRY RUN] Plan generated — skipping execution")
            _store.update(
                job_id, state=JobState.COMPLETED, done=True,
                phase=Phase.DONE, progress=1.0,
                summary=f"[Dry run] {plan.summary}\n\nSteps:\n" +
                        "\n".join(f"  {s.id}. [{s.action.value}] {s.description}" for s in plan.steps),
            )
            machine.force_terminal(Phase.DONE)
            checkpoint.cleanup()
            return

        if _is_cancelled(job_id):
            return

        # ── EXECUTING ────────────────────────────────────────────────────
        machine.transition(Phase.EXECUTING)
        _store.update(job_id, phase=Phase.EXECUTING)
        executor = StepExecutor(project_root, checkpoint)

        step_results: list[StepResult] = []
        consecutive_failures = 0

        for i, step in enumerate(plan.steps):
            if _is_cancelled(job_id):
                return

            _store.update(
                job_id,
                current_step=step.description,
                step_index=i + 1,
                progress=(i / total),
            )
            log(f"Step {i + 1}/{total}: {step.description}")

            result = executor.execute_step(step)
            step_results.append(result)

            if result.success:
                consecutive_failures = 0
                log(f"  -> OK")
            else:
                consecutive_failures += 1
                log(f"  -> FAILED: {result.error}")
                if consecutive_failures >= config.CONSECUTIVE_FAILURE_LIMIT:
                    fail(f"Circuit breaker: {consecutive_failures} consecutive failures")
                    _rollback(checkpoint, log)
                    return

        # ── VERIFYING ────────────────────────────────────────────────────
        machine.transition(Phase.VERIFYING)
        _store.update(job_id, phase=Phase.VERIFYING, current_step="Verifying results")

        failed_steps = [r for r in step_results if not r.success]

        if not failed_steps:
            log("All steps passed verification")
            machine.transition(Phase.DONE)
            _store.update(
                job_id, phase=Phase.DONE, state=JobState.COMPLETED, done=True,
                progress=1.0,
                summary=_build_summary_v1(plan, step_results, executor, model_used, start_time),
            )
            checkpoint.cleanup()
            return

        # ── FIXING loop ──────────────────────────────────────────────────
        fixes_applied = 0
        for fix_round in range(config.MAX_FIXES_PER_STEP):
            if _is_cancelled(job_id):
                return

            machine.transition(Phase.FIXING)
            _store.update(job_id, phase=Phase.FIXING,
                          current_step=f"Fix round {fix_round + 1}")
            log(f"Fix round {fix_round + 1}: {len(failed_steps)} failed step(s)")

            new_results: list[StepResult] = []
            all_fixed = True

            for failed in failed_steps:
                error_context = f"Step {failed.step_id} failed.\nAction: {failed.action.value}\nTarget: {failed.target}\nError: {failed.error}\nStderr: {failed.stderr}"
                fix_prompt = f"## Failed Step\n{error_context}\n\n## Project\n{analysis_text}"

                try:
                    fix_resp, _ = call_llm_structured(
                        _FIXER_SYSTEM, fix_prompt, LLMFixResponse
                    )
                except LLMError:
                    log(f"  LLM fixer failed for step {failed.step_id}")
                    all_fixed = False
                    new_results.append(failed)
                    continue

                fix_step = PlanStep(
                    id=failed.step_id,
                    description=f"Fix: {fix_resp.diagnosis}",
                    action=fix_resp.fix_action,
                    target=fix_resp.target,
                    content=fix_resp.content,
                    command=fix_resp.command,
                    expected_outcome=fix_resp.expected_outcome,
                    confidence=fix_resp.confidence,
                )

                machine.transition(Phase.EXECUTING)
                _store.update(job_id, phase=Phase.EXECUTING)

                fix_result = executor.execute_step(fix_step)
                fixes_applied += 1

                if fix_result.success:
                    log(f"  Fixed step {failed.step_id}: {fix_resp.diagnosis}")
                    new_results.append(fix_result)
                else:
                    log(f"  Fix failed for step {failed.step_id}")
                    all_fixed = False
                    new_results.append(fix_result)

                machine.transition(Phase.VERIFYING)
                _store.update(job_id, phase=Phase.VERIFYING)

            failed_steps = [r for r in new_results if not r.success]

            if all_fixed or not failed_steps:
                break

        # ── final verdict ────────────────────────────────────────────────
        if failed_steps:
            log(f"{len(failed_steps)} step(s) still failing after fixes — rolling back")
            _rollback(checkpoint, log)
            fail(f"{len(failed_steps)} step(s) could not be fixed")
        else:
            machine.force_terminal(Phase.DONE)
            _store.update(
                job_id, phase=Phase.DONE, state=JobState.COMPLETED, done=True,
                progress=1.0,
                summary=_build_summary_v1(plan, step_results, executor, model_used, start_time, fixes_applied),
            )
            checkpoint.cleanup()

    except Exception as exc:
        tb = traceback.format_exc()
        _store.update(
            job_id, state=JobState.FAILED,
            error=f"Unexpected error: {exc}",
            log_line=f"FATAL: {tb[-500:]}",
            done=True,
        )
        try:
            _rollback(checkpoint, log)
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════════
#  v2 — agentic loop with task decomposition
# ═════════════════════════════════════════════════════════════════════════════

def _run_job_v2(
    job_id: str,
    goal: str,
    project_root: Path,
    context: Optional[str],
    analysis,
    analysis_text: str,
    parsed_goal,
    log,
) -> None:
    from agents.maya_code.agentic_loop import run_subtask
    from agents.maya_code.deep_analyzer import deep_analyze
    from agents.maya_code.decomposer import decompose
    from agents.maya_code.tool_executor import ToolBelt

    start_time = time.time()

    def fail(msg: str) -> None:
        _store.update(job_id, state=JobState.FAILED, error=msg, done=True)

    try:
        _store.update(job_id, version="v2")

        # ── Deep analysis ────────────────────────────────────────────────
        log("Deep-analyzing project files...")
        _store.update(job_id, current_step="Reading key files")
        deep_context = deep_analyze(project_root, analysis, parsed_goal)

        if _is_cancelled(job_id):
            return

        # ── Decompose into subtask DAG ───────────────────────────────────
        _store.update(job_id, phase=Phase.PLANNING, current_step="Decomposing into subtasks")
        log("Decomposing goal into subtasks...")
        graph = decompose(parsed_goal, analysis_text, deep_context)

        total_subtasks = len(graph.subtasks)
        log(f"Decomposed into {total_subtasks} subtask(s): {', '.join(st.title for st in graph.subtasks)}")

        _store.update(
            job_id,
            total_subtasks=total_subtasks,
            total_steps=total_subtasks,
            subtasks=_serialize_subtasks(graph.subtasks),
        )

        if _is_cancelled(job_id):
            return

        # ── Execute subtasks in topological order ────────────────────────
        _store.update(job_id, phase=Phase.EXECUTING)
        subtask_map = {st.id: st for st in graph.subtasks}
        all_files_created: list[str] = []
        all_files_modified: list[str] = []

        for idx, st_id in enumerate(graph.execution_order):
            if _is_cancelled(job_id):
                return

            subtask = subtask_map[st_id]

            # Check dependencies
            deps_ok = all(
                subtask_map[dep].state == SubtaskState.COMPLETED
                for dep in subtask.depends_on
                if dep in subtask_map
            )
            if not deps_ok:
                subtask.state = SubtaskState.SKIPPED
                subtask.error = "Dependency failed"
                log(f"Skipping subtask [{st_id}] {subtask.title} — dependency not met")
                _store.update(
                    job_id,
                    subtask_index=idx + 1,
                    subtasks=_serialize_subtasks(graph.subtasks),
                    current_subtask=subtask.title,
                    current_step=f"Skipped: {subtask.title}",
                )
                continue

            log(f"── Subtask {idx + 1}/{total_subtasks}: {subtask.title} ──")
            _store.update(
                job_id,
                subtask_index=idx + 1,
                current_subtask=subtask.title,
                current_step=subtask.title,
                progress=idx / total_subtasks,
                subtasks=_serialize_subtasks(graph.subtasks),
            )

            # Per-subtask checkpoint
            cp = CheckpointManager(f"{job_id}/{st_id}", project_root)
            tool_belt = ToolBelt(project_root, cp)

            subtask = run_subtask(
                subtask=subtask,
                parsed_goal=parsed_goal,
                analysis_text=analysis_text,
                tool_belt=tool_belt,
                log_fn=log,
                cancel_check=lambda: _is_cancelled(job_id),
            )
            subtask_map[st_id] = subtask

            if subtask.state == SubtaskState.COMPLETED:
                log(f"  Subtask completed: {subtask.summary or 'OK'}")
                cp.cleanup()
                all_files_created.extend(tool_belt.files_created)
                all_files_modified.extend(tool_belt.files_modified)
            elif subtask.state == SubtaskState.FAILED:
                log(f"  Subtask failed: {subtask.error}")
                has_work = bool(tool_belt.files_created or tool_belt.files_modified)
                if has_work and "budget" not in (subtask.error or "").lower():
                    _rollback(cp, log)
                elif has_work:
                    log(f"  Keeping partial work ({len(tool_belt.files_created)} created, {len(tool_belt.files_modified)} modified)")
                    cp.cleanup()
                    all_files_created.extend(tool_belt.files_created)
                    all_files_modified.extend(tool_belt.files_modified)
                else:
                    _rollback(cp, log)

            _store.update(
                job_id,
                subtasks=_serialize_subtasks(graph.subtasks),
                log_line=f"  [{subtask.state.value}] {subtask.title}",
            )

        # ── Final verdict ────────────────────────────────────────────────
        completed = [st for st in graph.subtasks if st.state == SubtaskState.COMPLETED]
        failed = [st for st in graph.subtasks if st.state == SubtaskState.FAILED]
        skipped = [st for st in graph.subtasks if st.state == SubtaskState.SKIPPED]
        elapsed = time.time() - start_time

        summary_lines = [
            f"Goal: {goal}",
            f"Subtasks: {len(completed)} completed, {len(failed)} failed, {len(skipped)} skipped",
            f"Duration: {elapsed:.1f}s",
        ]
        if all_files_created:
            summary_lines.append(f"Created: {', '.join(all_files_created[:15])}")
        if all_files_modified:
            summary_lines.append(f"Modified: {', '.join(all_files_modified[:15])}")

        if failed:
            summary_lines.append(f"\nFailed subtasks:")
            for st in failed:
                summary_lines.append(f"  - {st.title}: {st.error}")

        final_state = JobState.COMPLETED if not failed else JobState.FAILED
        _store.update(
            job_id,
            phase=Phase.DONE,
            state=final_state,
            done=True,
            progress=1.0,
            summary="\n".join(summary_lines),
            subtasks=_serialize_subtasks(graph.subtasks),
        )

    except Exception as exc:
        tb = traceback.format_exc()
        _store.update(
            job_id, state=JobState.FAILED,
            error=f"Unexpected error: {exc}",
            log_line=f"FATAL: {tb[-500:]}",
            done=True,
        )


# ═════════════════════════════════════════════════════════════════════════════
#  Shared helpers
# ═════════════════════════════════════════════════════════════════════════════

def _is_cancelled(job_id: str) -> bool:
    snap = _store.get(job_id)
    return snap is not None and snap.state == JobState.CANCELLED


def _rollback(checkpoint: CheckpointManager, log) -> None:
    if checkpoint.entry_count > 0:
        log("Rolling back changes...")
        lines = checkpoint.rollback()
        for line in lines:
            log(f"  {line}")
    checkpoint.cleanup()


def _build_summary_v1(
    plan: CodingPlan,
    results: list[StepResult],
    executor: StepExecutor,
    model: str,
    start: float,
    fixes: int = 0,
) -> str:
    elapsed = time.time() - start
    ok = sum(1 for r in results if r.success)
    fail_count = sum(1 for r in results if not r.success)
    lines = [
        f"Goal: {plan.goal}",
        f"Steps: {ok} passed, {fail_count} failed, {fixes} fixes applied",
        f"Duration: {elapsed:.1f}s | Model: {model}",
    ]
    if executor.files_created:
        lines.append(f"Created: {', '.join(executor.files_created[:10])}")
    if executor.files_modified:
        lines.append(f"Modified: {', '.join(executor.files_modified[:10])}")
    if executor.files_deleted:
        lines.append(f"Deleted: {', '.join(executor.files_deleted[:10])}")
    return "\n".join(lines)


def _serialize_subtasks(subtasks) -> list[dict]:
    """Compact subtask summaries for the job store / frontend."""
    return [
        {
            "id": st.id,
            "title": st.title,
            "state": st.state.value,
            "actions_used": st.actions_used,
            "action_budget": st.action_budget,
            "error": st.error,
            "summary": st.summary,
        }
        for st in subtasks
    ]
