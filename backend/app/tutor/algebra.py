"""Equations in one unknown, read from the student's own words, for code's checks (no model, no free evaluation).

Only numbers, one single-letter unknown, + - * / and powers are read (implicit products like 2w and w(w + 2) included);
anything else in a clause is skipped. Used to check a stated value by substitution: "w = 6" is worked when the same
answer has another equation in w that 6 satisfies, and 6 satisfies every equation in w the student wrote correctly.
"""

import ast
import operator
import re
from typing import NamedTuple

_CLAUSES = re.compile(r"(?<!\d)[.;,:]|[.;,:](?!\d)|\n|\b(?:so|or|and|gives|giving|then|hence|therefore|thus|which)\b", re.I)
_SYMBOLS = str.maketrans({"−": "-", "–": "-", "—": "-", "×": "*", "·": "*", "÷": "/", "^": "**"})
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
TOLERANCE = 1e-6


class Equation(NamedTuple):
    variable: str
    left: ast.expr
    right: ast.expr
    assignment: float | None  # set when the equation is "variable = number"


def _expression(text: str) -> ast.expr | None:
    text = text.strip().translate(_SYMBOLS).replace("²", "**2").replace("³", "**3")
    text = re.sub(r"\\[()\[\]]|\\,|\$", "", text)  # LaTeX delimiters and spacing
    text = re.sub(r"(?<![a-zA-Z])[a-zA-Z]{2,3}(?![a-zA-Z])", lambda m: "*".join(m.group()), text)  # 2gh, mgh
    text = re.sub(r"(\d)\s*([a-zA-Z(])", r"\1*\2", text)  # 2w, 2(w + 1)
    text = re.sub(r"\)\s*([a-zA-Z0-9(])", r")*\1", text)  # (w + 8)(w - 6), (w)2
    text = re.sub(r"\b([a-zA-Z])\s*\(", r"\1*(", text)  # w(w + 2)
    if not text or not re.fullmatch(r"[\s\d.a-zA-Z+\-*/()]+", text):
        return None
    try:
        tree = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, *_OPS)):
            return None
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            return None
        if isinstance(node, ast.Name) and len(node.id) != 1:
            return None
    return tree


def _nearest(side: str, from_end: bool) -> ast.expr | None:
    """The longest readable expression at the end of a left side, or at the start of a right side."""
    words = side.split()
    spans = ([words[i:] for i in range(len(words))] if from_end else [words[:i] for i in range(len(words), 0, -1)])
    for span in spans:
        # A word at the far edge is not math: "I used v^2" (a leading word, a lone letter there is the unknown) and
        # "20.4 m" (a trailing word or unit).
        edge = span[0] if from_end else span[-1]
        if len(span) > 1 and edge.isalpha() and (len(edge) > 1 or not from_end):
            continue
        tree = _expression(" ".join(span))
        if tree is not None:
            return tree
    return None


def value(tree: ast.expr, variable: str | None = None, x: float = 0.0) -> float:
    if isinstance(tree, ast.Constant):
        return float(tree.value)
    if isinstance(tree, ast.Name):
        if tree.id != variable:
            raise ValueError("another unknown")
        return x
    if isinstance(tree, ast.UnaryOp):
        return _OPS[type(tree.op)](value(tree.operand, variable, x))
    if isinstance(tree, ast.BinOp):
        return _OPS[type(tree.op)](value(tree.left, variable, x), value(tree.right, variable, x))
    raise ValueError("not an expression")


def _names(tree: ast.expr) -> set[str]:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def _pairs(text: str):
    """Each "left = right" the text writes, as expressions (chains like "w = (-2 + 14)/2 = 6" read pairwise)."""
    for clause in _CLAUSES.split(text):
        if not clause or "=" not in clause:
            continue
        # Words around an equation are not part of it ("the length is w + 2 = 8 m", "0 factors as (w + 6)(w - 8)"):
        # each side keeps its longest readable part next to the "=".
        parts = clause.split("=")
        for raw_left, raw_right in zip(parts, parts[1:]):
            left, right = _nearest(raw_left, from_end=True), _nearest(raw_right, from_end=False)
            if left is not None and right is not None:
                yield left, right


def formula_unknowns(text: str) -> set[str]:
    """Unknowns that appear in a formula of several unknowns the text writes (v^2 = u^2 - 2gh names h)."""
    return {name for left, right in _pairs(text) if len(_names(left) | _names(right)) > 1
            for name in _names(left) | _names(right)}


def equations(text: str) -> list[Equation]:
    """Every equation in one unknown written in the text."""
    found = []
    for left, right in _pairs(text):
        names = _names(left) | _names(right)
        if len(names) != 1:
            continue
        (variable,) = names
        assignment = None
        if isinstance(left, ast.Name) and not _names(right):
            assignment = value(right)
        elif isinstance(right, ast.Name) and not _names(left):
            assignment = value(left)
        found.append(Equation(variable, left, right, assignment))
    return found


def _decimals(x: float) -> int:
    text = repr(float(x))
    return 0 if text.endswith(".0") or "e" in text else len(text.split(".")[1])


def holds(equation: Equation, x: float) -> bool:
    """Whether x satisfies the equation; a value written with decimals is allowed its rounding (t = 2.04 for 2.0408:
    the true root lies within half its last digit), a whole number must fit exactly."""

    def gap(at: float) -> float:
        return value(equation.left, equation.variable, at) - value(equation.right, equation.variable, at)

    try:
        here = gap(x)
        if abs(here) <= TOLERANCE * max(1.0, abs(value(equation.left, equation.variable, x))):
            return True
        decimals = _decimals(x)
        if not decimals:
            return False
        half = 0.5 * 10 ** -decimals
        return gap(x - half) * gap(x + half) <= 0
    except (ValueError, ZeroDivisionError, OverflowError):
        return False


def numeric_results(text: str) -> set[float]:
    """Results of the numeric computations the text writes, parentheses and powers included (20(2.04) - 4.9(2.04)^2 =
    20.4), each true to the precision the student wrote."""
    found = set()
    for left, right in _pairs(text):
        if _names(left) or _names(right) or not isinstance(right, ast.Constant) or isinstance(left, ast.Constant):
            continue
        try:
            computed, stated = value(left), value(right)
        except (ValueError, ZeroDivisionError, OverflowError):
            continue
        if abs(computed - stated) <= max(0.005, 0.5 * 10 ** -_decimals(stated)) + 1e-9 * abs(stated):
            found.add(round(stated, 6))
    return found


def worked_roots(answer: str, earlier: list[str]) -> dict[str, set[float]]:
    """Values of an unknown the answer works out. A stated value ("w = 6") counts when the same answer shows how it was
    found: another equation in that unknown that it satisfies (the derivation), or a named formula with that unknown
    in it ("v^2 = u^2 - 2gh, so h = 20.4"). Either way it must satisfy every equation in that one unknown the student
    wrote, here and in earlier correct work; a value alone, with nothing in its answer behind it, never counts."""
    here = equations(answer)
    formulas = formula_unknowns(answer)
    everywhere = here + [e for text in earlier for e in equations(text)]
    roots: dict[str, set[float]] = {}
    for eq in here:
        if eq.assignment is None:
            continue
        others = [e for e in here if e.variable == eq.variable and e.assignment is None]
        consistent = [e for e in everywhere if e.variable == eq.variable and e.assignment is None]
        stated = {e.assignment for e in here if e.variable == eq.variable and e.assignment is not None}
        if (others or eq.variable in formulas) and all(
            holds(e, eq.assignment) or _other_case(e, eq.assignment, stated, consistent, here) for e in consistent
        ):
            roots.setdefault(eq.variable, set()).add(round(eq.assignment, 6))
    return roots


def _other_case(case: Equation, x: float, stated: set[float], consistent: list[Equation], here: list[Equation]) -> bool:
    """Whether an equation x fails is another case of the same split: "w + 8 = 0 or w - 6 = 0, so w = -8 or w = 6"
    after "(w + 8)(w - 6) = 0". It is, when it is in this answer, another value the answer states solves it, and an
    equation the student wrote is solved by both (the one split into cases). x must satisfy every other equation."""
    return case in here and any(
        y != x and holds(case, y) and any(e is not case and holds(e, x) and holds(e, y) for e in consistent)
        for y in stated
    )


def constant_sides(equation: Equation) -> set[float]:
    """The numbers that make up a whole side of an equation in its unknown (the 0 of "w² + 2w - 48 = 0")."""
    return {round(value(side), 6) for side in (equation.left, equation.right) if not _names(side)}


def derived_values(answer: str, roots: dict[str, set[float]]) -> set[float]:
    """Numbers the answer gets from a worked root: "w + 2 = 8" with w = 6 worked gives 8."""
    found = set()
    for eq in equations(answer):
        for x in roots.get(eq.variable, ()):
            for side, other in ((eq.left, eq.right), (eq.right, eq.left)):
                if not _names(other) and _names(side) and holds(eq, x):
                    found.add(round(value(other), 6))
    return found


# Points to compare two equations at: not whole numbers, so they miss the roots and poles students' equations have.
_PROBES = (-7.31, -3.17, -1.73, 0.41, 1.93, 3.71, 5.29, 11.13)


def equivalent(a: Equation, b: Equation) -> bool:
    """Whether two equations in the same unknown are one equation up to a nonzero factor, so they have the same
    solutions: "(w + 8)(w - 6) = 0", "w² + 2w - 48 = 0" and "w(w + 2) = 48" all are. Their left-minus-right sides must
    agree, up to one constant factor, at every probe point; that decides it for polynomials up to degree seven. An
    identity (both sides always equal) is no equation and is equivalent to nothing."""
    if a.variable != b.variable:
        return False
    ratio = None
    try:
        for x in _PROBES:
            fa = value(a.left, a.variable, x) - value(a.right, a.variable, x)
            fb = value(b.left, b.variable, x) - value(b.right, b.variable, x)
            scale = max(1.0, abs(fa), abs(fb))
            if abs(fb) <= TOLERANCE * scale:
                if abs(fa) > TOLERANCE * scale:
                    return False
                continue
            if ratio is None:
                ratio = fa / fb
            elif abs(fa / fb - ratio) > TOLERANCE * max(1.0, abs(ratio)):
                return False
    except (ValueError, ZeroDivisionError, OverflowError):
        return False
    return ratio is not None and abs(ratio) > TOLERANCE
