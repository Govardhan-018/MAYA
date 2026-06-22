"""State machine for the coding loop.

Allowed transitions are encoded in a static table. Any attempt to make an
illegal transition raises ``IllegalTransition``.  This is the only place
phase transitions happen — the runner calls ``transition()`` and nothing else.
"""

from __future__ import annotations

from agents.maya_code.contracts import Phase


class IllegalTransition(Exception):
    """Raised when a disallowed phase transition is attempted."""


# ── transition table ──────────────────────────────────────────────────────────
# key = current phase, value = set of allowed next phases
_TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.ANALYZING: frozenset({Phase.PLANNING}),
    Phase.PLANNING:  frozenset({Phase.EXECUTING}),
    Phase.EXECUTING: frozenset({Phase.VERIFYING}),
    Phase.VERIFYING: frozenset({Phase.DONE, Phase.FIXING}),
    Phase.FIXING:    frozenset({Phase.EXECUTING}),
    Phase.DONE:      frozenset(),
}


class PhaseMachine:
    """Guards phase transitions for one job."""

    def __init__(self) -> None:
        self._phase: Phase = Phase.ANALYZING

    @property
    def phase(self) -> Phase:
        return self._phase

    def transition(self, target: Phase) -> None:
        """Move to *target* if the transition is legal, else raise."""
        allowed = _TRANSITIONS.get(self._phase, frozenset())
        if target not in allowed:
            raise IllegalTransition(
                f"Cannot transition from {self._phase.value} to {target.value}. "
                f"Allowed: {sorted(p.value for p in allowed)}"
            )
        self._phase = target

    def can_transition(self, target: Phase) -> bool:
        return target in _TRANSITIONS.get(self._phase, frozenset())

    def force_terminal(self, target: Phase) -> None:
        """Force to DONE (used on FAILED/CANCELLED where normal rules don't apply)."""
        if target != Phase.DONE:
            raise IllegalTransition("force_terminal only accepts DONE")
        self._phase = target
