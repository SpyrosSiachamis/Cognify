"""Correct-work resolution: a student's correction resolves the challenged step; it never starts a search for a new
one.

When the tutor has said one of the student's steps does not hold up, and the student's next answer proves every
value in that step with calculations that are true and built only on validated values, with no false calculation
and no new value anywhere the diagnosis calls wrong, the challenge is answered: code resolves the gap and the session
moves on. Bounded and deterministic: no model call and no recheck. Anything short of that proof leaves the
diagnosis exactly as it was, so a real error (a false calculation, a new or contradictory value) is still caught.

Validated values carry their provenance. A value is validated only when something derived it: the worked
solution, a step the diagnosis marked correct earlier in this cycle, or a true calculation in the answer whose
operands are given or already validated. The problem's own numbers (the givens) may be used in a calculation but
are never validated on their own, so restating the givens proves nothing.

A challenged equation in an unknown ("(w + 8)(w - 6) = 0") has no calculation to prove; it is established instead
when it is the same equation (algebra.equivalent) as one the student wrote in an earlier answer with no wrong step,
and the answer works from it: every value of the unknown it states solves both. A stale wrong label is cleared only
that way, by evidence that the claim holds, never because the answer is later or does not repeat it.
"""

import re
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict

from app.common.vocab import ResolutionState
from app.session.schema import Solution

from .algebra import (
    Equation, constant_sides, derived_values, equations, equivalent, holds, numeric_results, worked_roots,
)
from .consistency import _close
from .consistency import givens as given_values
from .evidence import arithmetic_holds, calculations, numeric_values, substantive
from .repair import gap_step
from .schema import PriorDiagnosis, Step, TutorDiagnosis

RESOLVED_REASON = "challenged step established by the student's own correct calculations; no contradiction"
ESTABLISHED_REASON = "challenged equation established: the same equation as the student's earlier correct work, and their answer solves it"


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnosis: TutorDiagnosis  # the turn's diagnosis with the answered challenge resolved
    validated: list[float]  # the validated values it rests on (for the trace)
    established_equation: bool = False  # resolved by an equation the student's earlier work establishes


def validated_values(given: set[float], sources: list[str], text: str) -> set[float]:
    """Values derived by the solution or earlier correct work (sources), closed over the true calculations in text."""
    validated = set().union(*(numeric_values(t) for t in sources if arithmetic_holds(t))) - given
    usable = [c for c in calculations(text) if c.holds]
    grew = True
    while grew:
        grew = False
        for calc in usable:
            if calc.result not in validated and calc.result not in given and calc.operands <= given | validated:
                validated.add(calc.result)
                grew = True
    return validated


def contradictions(text: str, wrong: list[Step], given: set[float], validated: set[float]) -> list[str]:
    """What concretely speaks against the answer: a false calculation, or a value nothing derived in a step the
    diagnosis calls wrong."""
    found = ["a calculation that is not true" for c in calculations(text) if not c.holds]
    for step in wrong:
        unknown = numeric_values(step.quote or "") - given - validated
        if unknown:
            found.append(f'"{step.quote}" uses {sorted(unknown)}, which nothing derived')
    return found


def resolve_challenge(
    prior: PriorDiagnosis | None, diagnosis: TutorDiagnosis, attempt: str, given: set[float], sources: list[str],
    clean: list[str] = [],
) -> Resolution | None:
    """The diagnosis with the challenge resolved, if the answer establishes the challenged step; else None. clean:
    the student's correct steps from earlier answers with no wrong step (what a challenged equation may rest on)."""
    challenged = gap_step(prior.steps, prior.main_gap) if prior else None
    if challenged is None or challenged.status != "wrong" or not challenged.quote:
        return None
    if diagnosis.evidence != "sufficient" or diagnosis.response_to not in ("original_problem", "tutor_question"):
        return None
    validated = validated_values(given, sources, attempt)
    claims = established_equations(challenged.quote, attempt, clean)
    wrong = [s for s in diagnosis.steps if s.status == "wrong"]
    if claims:
        # Only a wrong step that restates the established equation is cleared; any other wrong step stands.
        if not all(_restates(s, claims) for s in wrong) or contradictions(attempt, [], given, validated):
            return None
    else:
        claimed = numeric_values(challenged.quote) - given
        # Established: every value the challenged step derived is now proven, by a true calculation in this answer.
        proven = {c.result for c in calculations(attempt) if c.holds}
        if not claimed or not claimed <= proven or not claimed <= validated:
            return None
        if contradictions(attempt, wrong, given, validated):
            return None
    steps = [s.model_copy(update={"status": "correct"}) if s.status == "wrong" else s for s in diagnosis.steps]
    resolved = TutorDiagnosis.model_validate({
        **diagnosis.model_dump(), "steps": [s.model_dump() for s in steps], "main_gap": None, "alternatives": [],
        "error": None,
    })
    return Resolution(diagnosis=resolved, validated=sorted(validated), established_equation=bool(claims))


def established_equations(claim: str, attempt: str, clean: list[str]) -> list[Equation]:
    """The equations of a challenged step, if every one is established by the student's evidence; else [].

    Established: the equation is the same equation as one in the student's earlier correct work from an answer with
    no wrong step (so never the answer that was challenged, and never the hidden solution), and this answer works from it:
    it states at least one value of the unknown, and every value it states solves both equations. A stated value that
    fails either one is a contradiction, and the label stands.
    """
    written = [e for e in equations(claim) if e.assignment is None]
    basis = [e for text in clean for e in equations(text) if e.assignment is None]
    found = []
    for eq in written:
        same = next((b for b in basis if equivalent(eq, b)), None)
        stated = [e.assignment for e in equations(attempt) if e.variable == eq.variable and e.assignment is not None]
        if same is None or not stated or not all(holds(eq, x) and holds(same, x) for x in stated):
            return []
        found.append(eq)
    return found


def _restates(step: Step, claims: list[Equation]) -> bool:
    """A step that says nothing but an established equation: pure math in its unknown, each equation in it the same as
    a claim ("(w + 8)(w - 6) = 0, so the width is -8 m" says more, and is not cleared)."""
    quote = step.quote or ""
    found = equations(quote)
    if not found or any(e.assignment is not None or not any(equivalent(e, c) for c in claims) for e in found):
        return False
    variables = {e.variable for e in found}
    words = re.sub(rf"(?<![^\W\d_])(?:{'|'.join(variables)})(?![^\W\d_])", "", quote)  # 2w, w(w + 2)
    return not re.search(r"[^\W\d_]", words)


# ---- where the student stands on the problem (the invariant behind support removal) ----

_VALUE = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")


def _in_order(text: str) -> list[float]:
    return [round(float(t.replace(",", "")), 6) for t in _VALUE.findall(text)]


def _matches(target: float, values: set[float]) -> bool:
    """Demonstrated, allowing the set-up step's rounding to whole numbers (126.6 for a written 127)."""
    slack = 0.5 + 1e-9 if float(target).is_integer() else 0.005
    return any(abs(target - v) <= slack for v in values)


class Standing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ResolutionState
    demonstrated: list[float]  # values the student's own work has demonstrated in this cycle
    current_target: str | None  # the first required solution step not yet demonstrated (backend only)


_ENUMERATOR = re.compile(r"^\s*(?:step\s*)?\d+\s*[.):]\s+", re.I)


class Target(NamedTuple):
    """One required step of the worked solution, and what shows it."""

    step: str
    value: float | None  # the quantity it ends at; None for an equation in an unknown
    equations: tuple[Equation, ...] = ()  # an equation step's equations (shown by an equivalent one)


def required_targets(solution: Solution, given: set[float]) -> list[Target]:
    """The worked-solution steps the answer depends on, each with what it ends at.

    A step that ends at a quantity (a result) is required when that result feeds the answer: a later step uses it, or
    it is in the final result. A side calculation nothing uses afterwards (15% of 216 replaced one-for-one: 32.4) is
    not required. Step numbers ("7.") are not values. A step that ends at an equation in an unknown ("w² + 2w - 48 =
    0") ends at no quantity: the number on a side of it is part of the equation, so the target is the equation itself,
    shown by the student writing the same equation in any form (or by later worked values, like every target). The
    targets are only what the solution derives: nothing the tutor might ask afterwards is one.
    """
    steps = [_ENUMERATOR.sub("", step) for step in solution.steps]
    results = []
    for step in steps:
        derived = [v for v in _in_order(step) if v not in given]
        results.append(derived[-1] if derived else None)
    final = set(numeric_values(solution.result))
    targets = []
    for i, (step, result) in enumerate(zip(steps, results)):
        if result is None:
            continue
        found = equations(step)
        unknown = [e for e in found if e.assignment is None]
        quantity = result in numeric_results(step) or any(e.assignment == result for e in found)
        if not quantity and any(result in constant_sides(e) for e in unknown):
            targets.append(Target(solution.steps[i], None, tuple(unknown)))
            continue
        later = set().union(*(set(_in_order(s)) for s in steps[i + 1:])) | final
        if _matches(result, later):
            targets.append(Target(solution.steps[i], result))
    return targets


def _written(target: Target, texts: list[str]) -> bool:
    """An equation target the student wrote, in any equivalent form."""
    return any(equivalent(e, t) for text in texts for e in equations(text) for t in target.equations)


def worked_values(texts: list[str], known: set[float]) -> tuple[set[float], set[float]]:
    """Values the student reached with worked evidence, whatever route they took (never a value merely stated).

    Shown: the result of a true computation the student wrote (arithmetic, percentages, parentheses and powers), or a
    value of an unknown checked by substitution ("w = 6" after "(w + 8)(w - 6) = 0", consistent with every equation in
    w they wrote; or after a named formula with w in it) and values worked out from it ("the length is w + 2 = 8", in
    the same answer or a later one).
    Traceable: the shown values whose inputs are also accounted for (the givens, the factors their percentages imply
    and the sums of their ratio parts, values established before this answer, values written before the calculation,
    or other traceable values). Only a traceable value may stand in for steps the student skipped: a lone "24 ÷ 6 = 4"
    shows the 4 but does not account for the steps that make 24.
    """
    traceable: set[float] = set()
    # Each calculation, with the numbers the student wrote before it (in earlier work and earlier in the same text).
    calcs = [(c, set().union(*(numeric_values(t) for t in texts[:i])) | numeric_values(text[:c.at]))
             for i, text in enumerate(texts) for c in calculations(text) if c.holds]
    grew = True
    while grew:
        grew = False
        for calc, stated in calcs:
            if calc.result not in traceable and all(_close(o, known | traceable | stated) for o in calc.operands):
                traceable.add(calc.result)
                grew = True
    algebraic: set[float] = set()
    worked: dict[str, set[float]] = {}  # roots worked so far: a later answer may build on them ("w + 2 = 8")
    for i, text in enumerate(texts):
        for variable, values in worked_roots(text, texts[:i]).items():
            worked.setdefault(variable, set()).update(values)
        algebraic |= {x for values in worked.values() for x in values} | derived_values(text, worked)
    shown = {c.result for c, _ in calcs} | algebraic | {v for t in texts for v in numeric_results(t)}
    return shown | traceable, traceable | algebraic


def standing(
    solution: Solution, problem: str, diagnosis: TutorDiagnosis, attempt: str, earlier_correct: list[str],
    earlier_clean: list[str],
) -> Standing:
    """Code's reading of where the student stands, from their own evidence only (never the solution's values,
    never the givens alone, never the wording of the answer).

    PROBLEM_RESOLVED: every required step shown (demonstrated, or covered by a later required value or the final result
    the student reached with worked evidence, by any valid route), the final result itself worked, every written
    calculation true and no wrong step; only answers with no wrong step count (earlier_clean), so a correct calculation
    next to a wrong claim never resolves it on a later turn. CURRENT_TARGET_RESOLVED: the step that was current at the
    start of this turn is now shown. PREVIOUS_STEPS_CORRECT: earlier steps are shown and this turn adds no wrong step and
    no new claim. Anything else is CURRENT_TARGET_UNRESOLVED.
    """
    given = set(numeric_values(problem))
    turn_correct = [s.quote or "" for s in diagnosis.steps if s.status == "correct"]
    wrong = any(s.status == "wrong" for s in diagnosis.steps)

    def plain(quotes: list[str]) -> list[str]:
        # In an equation with an unknown the numbers are coefficients, not quantities the student established: such
        # a statement counts only through the values it works out (worked_values), never by a number appearing in it.
        return [q for q in quotes if not equations(q)]

    before = validated_values(given, plain(earlier_correct), "")
    now = validated_values(given, plain(earlier_correct + turn_correct), "" if equations(attempt) else attempt)
    clean = validated_values(given, plain(earlier_clean + turn_correct), "" if equations(attempt) else attempt)
    ratio_sums = {float(sum(int(p) for p in m if p)) for m in re.findall(r"(\d+)\s*:\s*(\d+)(?:\s*:\s*(\d+))?", problem)}
    shown_work, traceable = worked_values(earlier_clean + ([attempt] if not wrong else []),
                                          given_values(problem) | ratio_sums | before)
    targets = required_targets(solution, given)
    finals = [v for v in numeric_values(solution.result) if v not in given]
    # What comes after each required step: reaching any of it with worked evidence covers the step (route-independent).
    # A final result covers the steps leading to it, never another final result (the width does not give the length).
    later = [[t.value for t in targets[i + 1:] if t.value is not None]
             + ([] if t.value is not None and any(_matches(f, {t.value}) for f in finals) else finals)
             for i, t in enumerate(targets)]
    clean_texts = earlier_clean + ([attempt] if not wrong else [])

    def done(target: Target, values: set[float], texts: list[str]) -> bool:
        return _written(target, texts) if target.value is None else _matches(target.value, values)

    def shown(i: int, values: set[float], texts: list[str]) -> bool:
        return (done(targets[i], values | shown_work, texts) or any(_matches(v, traceable) for v in later[i]))

    open_before = next((t for t in targets if not done(t, before, earlier_clean)), None)
    open_now = next((t for i, t in enumerate(targets) if not shown(i, now, clean_texts)), None)
    if targets or finals:
        resolved = (all(shown(i, clean, clean_texts) for i in range(len(targets)))
                    and all(_matches(f, shown_work) for f in finals) and arithmetic_holds(attempt))
    else:
        # A non-numeric answer: a conclusion the diagnosis positively accepts, from work on this problem.
        resolved = diagnosis.evidence == "sufficient" and diagnosis.response_to == "original_problem" and any(
            s.role == "interpret" and s.status == "correct" and substantive(s.quote) for s in diagnosis.steps
        )
    # Only a usable reading with sufficient evidence can vouch that nothing in the answer is wrong (a failed or
    # insufficient diagnosis never resolves the problem, whatever the text shows).
    if resolved and not wrong and diagnosis.evidence == "sufficient":
        state: ResolutionState = "PROBLEM_RESOLVED"
    elif open_before is not None and (done(open_before, now, clean_texts) or open_now is None
                                      or targets.index(open_now) > targets.index(open_before)):
        state = "CURRENT_TARGET_RESOLVED"
    elif before and not wrong and all(v in given or _matches(v, before) for v in numeric_values(attempt)):
        state = "PREVIOUS_STEPS_CORRECT"
    else:
        state = "CURRENT_TARGET_UNRESOLVED"
    return Standing(state=state, demonstrated=sorted(now | shown_work), current_target=open_now.step if open_now else None)
