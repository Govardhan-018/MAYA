"""Thread-safe in-memory job store with JSON disk mirror.

Every mutation to a job's status goes through ``update()`` which:
1. Acquires the per-store lock.
2. Updates the in-memory ``StatusSnapshot``.
3. Writes a JSON mirror to ``system/code_jobs/{job_id}.json``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agents.maya_code import config
from agents.maya_code.contracts import JobState, Phase, StatusSnapshot


class JobStore:
    """Global job store — one instance per Maya process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, StatusSnapshot] = {}
        self._disk = config.JOBS_DIR
        self._disk.mkdir(parents=True, exist_ok=True)

    def create(self, job_id: str, goal: str, *, dry_run: bool = False) -> StatusSnapshot:
        now = datetime.now(timezone.utc).isoformat()
        snap = StatusSnapshot(
            job_id=job_id,
            state=JobState.PENDING,
            phase=Phase.ANALYZING,
            goal=goal,
            started_at=now,
            updated_at=now,
            dry_run=dry_run,
        )
        with self._lock:
            self._jobs[job_id] = snap
            self._mirror(snap)
        return snap

    def update(
        self,
        job_id: str,
        *,
        state: Optional[JobState] = None,
        phase: Optional[Phase] = None,
        current_step: Optional[str] = None,
        step_index: Optional[int] = None,
        total_steps: Optional[int] = None,
        progress: Optional[float] = None,
        log_line: Optional[str] = None,
        summary: Optional[str] = None,
        error: Optional[str] = None,
        done: Optional[bool] = None,
    ) -> StatusSnapshot:
        with self._lock:
            snap = self._jobs.get(job_id)
            if snap is None:
                raise KeyError(f"Unknown job: {job_id}")

            if state is not None:
                snap.state = state
            if phase is not None:
                snap.phase = phase
            if current_step is not None:
                snap.current_step = current_step
            if step_index is not None:
                snap.step_index = step_index
            if total_steps is not None:
                snap.total_steps = total_steps
            if progress is not None:
                snap.progress = min(max(progress, 0.0), 1.0)
            if log_line is not None:
                snap.log_tail.append(log_line)
                if len(snap.log_tail) > config.MAX_LOG_TAIL:
                    snap.log_tail = snap.log_tail[-config.MAX_LOG_TAIL:]
            if summary is not None:
                snap.summary = summary
            if error is not None:
                snap.error = error
            if done is not None:
                snap.done = done

            snap.updated_at = datetime.now(timezone.utc).isoformat()
            self._mirror(snap)
            return snap.model_copy()

    def get(self, job_id: str) -> Optional[StatusSnapshot]:
        with self._lock:
            snap = self._jobs.get(job_id)
            return snap.model_copy() if snap else None

    def list_jobs(self) -> list[StatusSnapshot]:
        with self._lock:
            return [s.model_copy() for s in self._jobs.values()]

    def cancel(self, job_id: str) -> Optional[StatusSnapshot]:
        with self._lock:
            snap = self._jobs.get(job_id)
            if snap is None:
                return None
            if snap.done:
                return snap.model_copy()
            snap.state = JobState.CANCELLED
            snap.done = True
            snap.updated_at = datetime.now(timezone.utc).isoformat()
            self._mirror(snap)
            return snap.model_copy()

    def _mirror(self, snap: StatusSnapshot) -> None:
        """Write snapshot to disk as JSON."""
        try:
            path = self._disk / f"{snap.job_id}.json"
            path.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
        except Exception:
            pass  # disk mirror is best-effort
