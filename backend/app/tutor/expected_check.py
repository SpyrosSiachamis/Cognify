"""Code's check of a generated expected solution (experimental). No model call; it verifies, it never corrects.

The set-up and follow-up models write the answer Cognify will judge the student against, and a generated answer can be
wrong (a 120 m² flower bed answered "8 m × 12 m", which is 96 m²). So the model also writes a small structured
candidate: the values of the problem's quantities and the problem's conditions as equations. Code evaluates them:

- VALID: every condition holds at the candidate's values, the conditions use every number in the problem, and every
  number in the stated answer is one of those values (to the precision the answer writes) or part of one's exact form.
- INVALID_EXPECTED_SOLUTION: a condition fails, or the stated answer is not the candidate's. The caller regenerates;
  code never swaps in an answer of its own.
- NOT_DETERMINISTICALLY_VERIFIABLE: no candidate, something code cannot read, or conditions that leave out a number
  of the problem (code cannot tell they encode this problem). The caller keeps its existing behaviour.

Read: numbers, names, + - * / and powers, sqrt (or √), percentages (25% is 25/100), implicit products (2w, 2sqrt(61),
w(2w - 4)). Nothing else: this is not a symbolic solver.
"""

import ast
import math
import operator
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence import numeric_values

# Exact values are expected (1 + sqrt(61), not 8.81), so a condition holds only up to floating-point error.
REL_TOL = 1e-9
MAX_EXPONENT = 10

Status = Literal["VALID", "INVALID_EXPECTED_SOLUTION", "NOT_DETERMINISTICALLY_VERIFIABLE"]


class ExpectedCheck(BaseModel):
    """The model's structured candidate. Code evaluates it; the model's own claims about it count for nothing."""

    model_config = ConfigDict(extra="forbid")

    # Each quantity's exact value, or an expression in quantities listed before it.
    values: dict[str, str] = Field(min_length=1)
    # The problem's conditions as equations in those quantities, using the problem's own numbers.
    conditions: list[str] = Field(min_length=1)


class ExpectedVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Status
    reason: str


class _Unreadable(ValueError):
    pass


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def _normalise(text: str) -> str:
    text = text.strip().translate(str.maketrans({"×": "*", "·": "*", "÷": "/", "−": "-", "–": "-", "^": "**"}))
    text = text.replace("²", "**2").replace("³", "**3")
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", text)
    text = re.sub(r"√\s*(\d+(?:\.\d+)?|[A-Za-z_]\w*)", r"sqrt(\1)", text).replace("√", "sqrt")
    text = re.sub(r"(\d)\s*([A-Za-z_(])", r"\1*\2", text)  # 2w, 2sqrt(61), 2(w + 1)
    text = re.sub(r"\)\s*([A-Za-z_\d(])", r")*\1", text)  # (w + 1)(w - 1)
    return re.sub(r"\b(?!sqrt\b)([A-Za-z_]\w*)\s*\(", r"\1*(", text)  # w(2w - 4)


def _parse(text: str) -> ast.expr:
    try:
        tree = ast.parse(_normalise(text), mode="eval").body
    except SyntaxError as exc:
        raise _Unreadable(f"cannot read {text!r}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id == "sqrt" and len(node.args) == 1
                    and not node.keywords):
                raise _Unreadable(f"cannot read {text!r}")
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise _Unreadable(f"cannot read {text!r}")
        elif not isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Name, ast.Load, ast.Pow, *_OPS)):
            raise _Unreadable(f"cannot read {text!r}")
    return tree


def _eval(tree: ast.expr, env: dict[str, float]) -> float:
    if isinstance(tree, ast.Constant):
        return float(tree.value)
    if isinstance(tree, ast.Name):
        if tree.id not in env:
            raise _Unreadable(f"{tree.id} has no value")
        return env[tree.id]
    if isinstance(tree, ast.UnaryOp):
        return _OPS[type(tree.op)](_eval(tree.operand, env))
    if isinstance(tree, ast.Call):
        return math.sqrt(_eval(tree.args[0], env))
    if isinstance(tree, ast.BinOp):
        left, right = _eval(tree.left, env), _eval(tree.right, env)
        if isinstance(tree.op, ast.Pow):
            if abs(right) > MAX_EXPONENT:
                raise _Unreadable("exponent too large")
            return left ** right
        return _OPS[type(tree.op)](left, right)
    raise _Unreadable("not an expression")


def _constants(tree: ast.expr) -> set[float]:
    return {round(float(n.value), 6) for n in ast.walk(tree) if isinstance(n, ast.Constant)}


def _equal(a: float, b: float) -> bool:
    return abs(a - b) <= REL_TOL * max(1.0, abs(a), abs(b))


def _decimals(number: str) -> int:
    return len(number.split(".")[1]) if "." in number else 0


def check_expected(candidate: ExpectedCheck | None, problem: str, answer: str) -> ExpectedVerdict:
    """Whether a generated answer satisfies its problem, by code. See the module docstring for the three outcomes."""
    if candidate is None:
        return ExpectedVerdict(status="NOT_DETERMINISTICALLY_VERIFIABLE", reason="no structured candidate")
    try:
        env: dict[str, float] = {}
        exact: set[float] = set()  # numbers in the values' exact forms (the 1 and 61 of "1 + √61")
        pending = dict(candidate.values)
        while pending:  # a value may use quantities listed in any order, as long as none is circular
            ready = {}
            for name, text in pending.items():
                tree = _parse(text)
                try:
                    ready[name] = _eval(tree, env)
                    exact |= _constants(tree)
                except _Unreadable:
                    continue
            if not ready:
                raise _Unreadable(f"cannot evaluate {', '.join(pending)}")
            env |= ready
            pending = {k: v for k, v in pending.items() if k not in ready}
        conditions = []
        for text in candidate.conditions:
            sides = text.replace("==", "=").split("=")
            if len(sides) != 2:
                raise _Unreadable(f"{text!r} is not one equation")
            conditions.append((text, _parse(sides[0]), _parse(sides[1])))
        results = [(text, _eval(left, env), _eval(right, env)) for text, left, right in conditions]
    except (_Unreadable, ArithmeticError, ValueError, OverflowError) as exc:
        return ExpectedVerdict(status="NOT_DETERMINISTICALLY_VERIFIABLE", reason=str(exc))

    used = set().union(*(_constants(left) | _constants(right) for _, left, right in conditions))
    missing = [n for n in sorted({abs(v) for v in numeric_values(problem)})
               if round(n, 6) not in used and round(n / 100, 6) not in used]
    if missing:
        return ExpectedVerdict(status="NOT_DETERMINISTICALLY_VERIFIABLE",
                               reason=f"the conditions do not use the problem's {', '.join(f'{n:g}' for n in missing)}")

    failed = [f"{text} gives {left:g} = {right:g}" for text, left, right in results if not _equal(left, right)]
    if failed:
        return ExpectedVerdict(status="INVALID_EXPECTED_SOLUTION", reason="; ".join(failed))

    stated = re.findall(r"-?\d+(?:\.\d+)?", answer.replace(",", ""))
    if not stated:
        return ExpectedVerdict(status="NOT_DETERMINISTICALLY_VERIFIABLE", reason="the answer states no number")
    values = list(env.values())

    def is_value(number: str) -> bool:
        x, slack = float(number), 0.5 * 10 ** -_decimals(number) if _decimals(number) else 0.0
        return any(abs(x - v) <= slack + REL_TOL * max(1.0, abs(v)) for v in values)

    strays = [n for n in stated if not is_value(n) and round(abs(float(n)), 6) not in exact]
    if strays or not any(is_value(n) for n in stated):
        return ExpectedVerdict(
            status="INVALID_EXPECTED_SOLUTION",
            reason=f"the stated answer {answer!r} is not the candidate's values "
                   f"({', '.join(f'{k} = {v:.6g}' for k, v in env.items())})",
        )
    return ExpectedVerdict(status="VALID", reason="every condition holds at the candidate's values")
