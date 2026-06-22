"""Runner — background thread that drives the full coding loop.

Lifecycle:  ``start_task()`` → spawns daemon thread → ANALYZING → PLANNING →
EXECUTING → VERIFYING → (FIXING loop) → DONE.

The runner owns the state machine, job store updates, checkpoint, and executor.
It never raises exceptions to the caller; every failure is caught and stored
in the job store as FAILED state.
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
    StepAction,
    StepResult,
    StatusSnapshot,
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


# ── prompts ───────────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """\
You are a precise coding planner. Given a project analysis and a user goal,
produce a step-by-step coding plan as JSON.

Rules:
- Each step must have: id (int), description, action (one of: create_file, modify_file, delete_file, run_command, install_deps, run_tests), target (file path), content (full file content for create/modify), command (for run/install/test), expected_outcome, confidence (0-1).
- File paths must be relative to the project root.
- For modify_file, provide the COMPLETE new file content, not a diff.
- Include a test step if possible.
- Keep the plan minimal — fewest steps to achieve the goal.

Respond ONLY with valid JSON matching this schema:
{"goal": str, "summary": str, "steps": [{"id": int, "description": str, "action": str, "target": str, "content": str|null, "command": str|null, "expected_outcome": str, "confidence": float}], "test_strategy": str}
"""

_FIXER_SYSTEM = """\
You are a coding error fixer. Given a failed step and its error output,
produce a single fix action as JSON.

Rules:
- Diagnose the root cause from the error output.
- Produce ONE fix action (create_file, modify_file, delete_file, run_command).
- For file actions, provide the COMPLETE file content.
- File paths must be relative to the project root.

Respond ONLY with valid JSON:
{"diagnosis": str, "fix_action": str, "target": str, "content": str|null, "command": str|null, "expected_outcome": str, "confidence": float}
"""


# ── runner ────────────────────────────────────────────────────────────────────

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


# ── background thread entry ──────────────────────────────────────────────────

def _run_job(
    job_id: str,
    goal: str,
    project_root: Path,
    dry_run: bool,
    context: Optional[str],
) -> None:
    """Main loop — runs in a daemon thread.  Never raises."""
    machine = PhaseMachine()
    checkpoint = CheckpointManager(job_id, project_root)
    model_used = ""
    start_time = time.time()

    def log(msg: str) -> None:
        _store.update(job_id, log_line=msg)

    def fail(msg: str) -> None:
        _store.update(job_id, state=JobState.FAILED, error=msg, done=True)
        machine.force_terminal(Phase.DONE)

    try:
        _store.update(job_id, state=JobState.RUNNING)

        # ── 1. ANALYZING ─────────────────────────────────────────────────
        log("Analyzing project structure...")
        _store.update(job_id, phase=Phase.ANALYZING, current_step="Scanning project")
        analysis = analyze_project(project_root)
        analysis_text = format_analysis_for_llm(analysis)
        log(f"Detected: {analysis.project_type} ({', '.join(analysis.languages[:5])})")

        if _is_cancelled(job_id):
            return

        # ── 2. PLANNING ──────────────────────────────────────────────────
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

        # ── 3. EXECUTING ─────────────────────────────────────────────────
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

        # ── 4. VERIFYING ─────────────────────────────────────────────────
        machine.transition(Phase.VERIFYING)
        _store.update(job_id, phase=Phase.VERIFYING, current_step="Verifying results")

        failed_steps = [r for r in step_results if not r.success]

        if not failed_steps:
            log("All steps passed verification")
            machine.transition(Phase.DONE)
            _store.update(
                job_id, phase=Phase.DONE, state=JobState.COMPLETED, done=True,
                progress=1.0,
                summary=_build_summary(plan, step_results, executor, model_used, start_time),
            )
            checkpoint.cleanup()
            return

        # ── 5. FIXING loop ───────────────────────────────────────────────
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
                summary=_build_summary(plan, step_results, executor, model_used, start_time, fixes_applied),
            )
            checkpoint.cleanup()

    except Exception as exc:
        tb = traceback.format_exc()
        _store.update(
            job_id,
            state=JobState.FAILED,
            error=f"Unexpected error: {exc}",
            log_line=f"FATAL: {tb[-500:]}",
            done=True,
        )
        try:
            _rollback(checkpoint, log)
        except Exception:
            pass


# ── helpers ───────────────────────────────────────────────────────────────────

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


def _build_summary(
    plan: CodingPlan,
    results: list[StepResult],
    executor: StepExecutor,
    model: str,
    start: float,
    fixes: int = 0,
) -> str:
    elapsed = time.time() - start
    ok = sum(1 for r in results if r.success)
    fail = sum(1 for r in results if not r.success)
    lines = [
        f"Goal: {plan.goal}",
        f"Steps: {ok} passed, {fail} failed, {fixes} fixes applied",
        f"Duration: {elapsed:.1f}s | Model: {model}",
    ]
    if executor.files_created:
        lines.append(f"Created: {', '.join(executor.files_created[:10])}")
    if executor.files_modified:
        lines.append(f"Modified: {', '.join(executor.files_modified[:10])}")
    if executor.files_deleted:
        lines.append(f"Deleted: {', '.join(executor.files_deleted[:10])}")
    return "\n".join(lines)
