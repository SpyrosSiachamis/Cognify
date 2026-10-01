"""Gap repair, decided by code from step evidence (not by the model's own judgement).

Repair means demonstrated improvement on the step where the gap showed. It is not
mastery: that still needs the stress test and the verdict.
"""

from app.common.vocab import GapType, StepRole, values

from .schema import PriorDiagnosis, Step

ROLE_ORDER: tuple[StepRole, ...] = values(StepRole)  # type: ignore[assignment]

# Where each kind of gap shows up first. Concept, self-correction and transfer gaps can sit
# at any step, so they use the order rule alone.
GAP_STEPS: dict[GapType, tuple[StepRole, ...]] = {
    "recognition": ("choose_method",),
    "strategy_choice": ("choose_method",),
    "representation": ("identify_quantities", "set_up", "interpret"),
    "procedure": ("substitute", "compute", "set_up"),
}


def _ordered(steps: list[Step]) -> list[Step]:
    return sorted(steps, key=lambda s: ROLE_ORDER.index(s.role))


def gap_step(steps: list[Step], gap: GapType | None = None) -> Step | None:
    """Where the gap shows: a wrong or missing step where this kind of gap lives, else the
    first wrong step, else the first missing one, in role order."""
    ordered = _ordered(steps)
    preferred = GAP_STEPS.get(gap, ()) if gap else ()
    for status in ("wrong", "missing"):
        for role in preferred:
            found = next((s for s in ordered if s.role == role and s.status == status), None)
            if found:
                return found
    # The step where this gap lives was not written at all, so it is missing.
    if preferred and not any(s.role in preferred for s in ordered):
        return Step(role=preferred[0], status="missing")
    return next((s for s in ordered if s.status == "wrong"), None) or next(
        (s for s in ordered if s.status == "missing"), None
    )


def repaired(prior: PriorDiagnosis | None, current: list[Step]) -> bool:
    """True when the step where the previous gap showed is now correct.

    Also true when every step is now correct and the previous turn had a gap.
    """
    if prior is None or prior.main_gap is None:
        return False
    if current and all(s.status == "correct" for s in current):
        return True
    before = gap_step(prior.steps, prior.main_gap)
    if before is None:
        return False
    now = next((s for s in current if s.role == before.role), None)
    return now is not None and now.status == "correct"
