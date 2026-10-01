"""Gap repair, decided by code from step evidence (not by the model's own judgement).

Repair means demonstrated improvement on the step where the gap showed. It is not
mastery: that still needs the stress test and the verdict.

The model proposes the step labels; code decides. A "correct" label at the gap step
counts only with new evidence in the student's own words, and only if the model's
own reading of the turn does not contradict it.
"""

from pydantic import BaseModel, ConfigDict

from app.common.vocab import GapType, StepRole, values

from .evidence import NOT_KNOWING, normalise
from .schema import PriorDiagnosis, Step, TutorDiagnosis

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


class RepairCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repaired: bool
    reason: str


def _not_repaired(reason: str) -> RepairCheck:
    return RepairCheck(repaired=False, reason=reason)


def assess_repair(prior: PriorDiagnosis | None, current: TutorDiagnosis) -> RepairCheck:
    """Decide repair from the step where the previous gap showed, using the student's evidence."""
    if prior is None or prior.main_gap is None:
        return _not_repaired("no gap was being taught")
    gap = prior.main_gap
    before = gap_step(prior.steps, gap)
    all_correct = bool(current.steps) and all(s.status == "correct" for s in current.steps)
    now = next((s for s in current.steps if before and s.role == before.role), None)

    if not all_correct:
        if before is None:
            return _not_repaired("the previous turn has no step where the gap showed")
        if now is None or now.status != "correct":
            status = now.status if now else "not written"
            return _not_repaired(f"{before.role} is still {status}")

    # New evidence: the student's own words now, not a restatement of not knowing or of last turn.
    evidence = now.quote if now is not None else None
    if now is not None:
        if not evidence or NOT_KNOWING.search(evidence):
            return _not_repaired(f"{now.role} is labelled correct but has no positive evidence")
        if any(normalise(evidence) == normalise(s.quote) for s in prior.steps if s.quote):
            return _not_repaired(f"{now.role} is labelled correct on evidence the student already gave last turn")

    # The model's own reading of this turn must not contradict the label.
    if current.main_gap == gap:
        return _not_repaired(f"conflict: the step is labelled correct but the diagnosis still finds a {gap} gap")
    rating = next((d.state for d in current.dimensions if d.name == gap), None)
    if rating in ("weak", "fragile"):
        return _not_repaired(f"partial: the {gap} dimension is still rated {rating}")

    where = f"{now.role}: \"{evidence}\"" if now is not None else "every step now holds"
    return RepairCheck(repaired=True, reason=f"{gap} gap repaired at {where}")


def repaired(prior: PriorDiagnosis | None, current: TutorDiagnosis) -> bool:
    return assess_repair(prior, current).repaired
