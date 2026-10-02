"""Is the student's own work on a fresh problem complete and internally consistent? Code only, no model call.

The judge compares an answer with the follow-up's generated rubric, and a generated rubric can be wrong. When the
judge says "incorrect", code reads the student's work: every calculation written must be true (arithmetic and
percentages), every value the student states must follow from the problem's own numbers or from values before it by
a true calculation (a step written out, or one plain operation left implicit, like "so 276 kg remain" after "24 kg
spoiled" from 300), and the final answer must follow from those values (rounding allowed). If all of that holds,
nothing in the student's work is wrong: the disagreement is with the rubric, and the student's shown work is taken
as the stronger evidence. One false calculation, or one value with no source, and the judge's verdict stands.

Known limit: internally consistent is not the same as right. A student who consistently applies a wrong idea (for
example a 4:7 split as 4/7 of the total) passes this check; that trade-off was chosen for the demo.
"""

import re
from itertools import product

from pydantic import BaseModel, ConfigDict

from .evidence import calculations, numeric_values

TOLERANCE = 0.005


class Consistency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consistent: bool
    reasons: list[str]  # why not (empty when consistent)


def _close(value: float, known: set[float]) -> bool:
    """Equal to a known value, allowing the rounding the student wrote (140.45 for 140.4545)."""
    decimals = len(f"{value}".split(".")[1]) if "." in f"{value}" and not f"{value}".endswith(".0") else 0
    slack = max(TOLERANCE, 0.5 * 10 ** -decimals + 1e-9) if decimals <= 2 else TOLERANCE
    return any(abs(value - k) <= slack + 1e-9 * abs(k) for k in known)


def _one_step(value: float, known: set[float], first: set[float] | None = None) -> bool:
    """Reachable from two known values by one plain operation (an implicit step: 300 - 24 = 276). With first, one of
    the two must come from it (a value stated on its own must build on the student's own work, not on givens alone)."""
    for a, b in product(first if first is not None else known, known):
        candidates = (a + b, a - b, a * b) + ((a / b,) if b else ())
        if any(abs(value - c) <= TOLERANCE + 1e-9 * abs(c) for c in candidates):
            return True
    return False


def givens(problem: str) -> set[float]:
    """The problem's numbers, with each percentage also as the factors it implies (25% -> 0.25, 1.25, 0.75)."""
    known = set(numeric_values(problem))
    for percent in re.findall(r"(\d+(?:\.\d+)?)\s*%", problem):
        p = float(percent) / 100
        known |= {round(p, 6), round(1 + p, 6), round(1 - p, 6)}
    return known


def check_work(text: str, problem: str) -> Consistency:
    reasons = [f"{c.result:g} does not follow from its own calculation" for c in calculations(text) if not c.holds]
    known = givens(problem)
    stated = numeric_values(text)
    if not stated - known:
        reasons.append("no work beyond the problem's own numbers")
    given = set(known)
    pending = set(stated) - known
    calcs = [c for c in calculations(text) if c.holds]
    grew = True
    while pending and grew:  # derive what can be derived, in any order, until nothing more follows
        grew = False
        for calc in calcs:
            # Inside a written calculation an operand may combine givens (276 × 4/11, with 11 = 4 + 7).
            if calc.result in pending and all(_close(o, known) or _one_step(o, known) for o in calc.operands):
                pending.discard(calc.result)
                known.add(calc.result)
                grew = True
        derived = known - given
        for value in list(pending):
            # A value stated on its own: equal (after rounding) to one already derived, or one plain step from one.
            if _close(value, derived) or (derived and _one_step(value, known, derived)):
                pending.discard(value)
                known.add(value)
                grew = True
    reasons += [f"{v:g} has no source in the problem or the work before it" for v in sorted(pending)]
    return Consistency(consistent=not reasons, reasons=reasons)
