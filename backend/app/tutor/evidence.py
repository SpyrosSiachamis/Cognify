"""Small helpers for reading the student's own words, shared by the reasoning rules and repair."""

import re
import unicodedata
from typing import NamedTuple

# Saying you do not know how to do a step is missing evidence (English and Greek, the supported languages).
NOT_KNOWING = re.compile(
    r"\b(i )?(do not|don't|dont) know\b|\bnot sure\b|\bno idea\b|\bi'?m stuck\b|\bcan'?t (figure|work) out\b"
    r"|δεν (το )?(ξέρω|ξερω|γνωρίζω|γνωριζω)|δεν είμαι σίγουρ|δεν ειμαι σιγουρ|καμία ιδέα|καμια ιδεα|κόλλησα|κολλησα",
    re.I,
)


def substantive(quote: str | None) -> bool:
    """Whether a quote says something beyond not knowing ("I don't know" alone is not evidence)."""
    if not quote:
        return False
    rest = NOT_KNOWING.sub(" ", normalise(quote))
    return len(re.findall(r"[\w.^/=+-]+", rest)) >= 4


def normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip(" .,;:!?\"'")


# ---- what a quote is about ----

# Function words long enough to pass the length cut (English and Greek, accents removed): they name nothing.
_FUNCTION_WORDS = frozenset("""
about after also been before being both could does each every find from have into many more most much must only
other same should some such than that their them then there these they this those very what when where which while
will with would your
αλλα αυτα αυτη αυτο αυτοι απο εχει εχουν ειναι εαν ενας κάθε καθε μετα μια οπου οταν ποια ποιο ποσα ποσες ποσο ποσοι
πριν τοτε βρειτε βρες
""".split())
_STEM = 5  # the same word in another form (width, widths; πλάτος, πλάτους) shares its first letters


def _content_words(text: str) -> set[str]:
    bare = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
    return {w[:_STEM] for w in re.findall(r"[^\W\d_]{4,}", bare) if w not in _FUNCTION_WORDS}


def refers_to_problem(quote: str, problem: str) -> bool:
    """Whether a quote is about the problem's own quantities: it states a value, or names something the problem
    names. A claim that names nothing of the problem (for example one about the student's own algebra) is not."""
    return bool(numeric_values(quote)) or bool(_content_words(quote) & _content_words(problem))


# Typographic variants of the same math, so a reformatted quote still matches the student's text.
_MATH = str.maketrans({"×": "*", "·": "*", "⋅": "*", "−": "-", "–": "-", "—": "-", "÷": "/", "²": "^2", "³": "^3"})
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[^\W\d_]+|[=+\-*/^<>]")


def _canon(text: str) -> str:
    text = normalise(text).translate(_MATH)
    return re.sub(r"\s*([=+\-*/^()<>])\s*", r"\1", text)


def quote_found(quote: str, attempt: str) -> bool:
    """Whether a quote is the student's own evidence: in their text up to formatting, or its words and
    numbers appear in the same order within a short stretch of it. Text from elsewhere does not match."""
    if _canon(quote) in _canon(attempt):
        return True
    # An explicit multiplication sign and an implicit one (4.9(2.04), 3x) are the same evidence.
    wanted = [t for t in _TOKEN.findall(_canon(quote)) if t != "*"]
    text = [t for t in _TOKEN.findall(_canon(attempt)) if t != "*"]
    if len(wanted) < 2:
        return False
    window = 2 * len(wanted) + 4
    for start, token in enumerate(text):
        if token != wanted[0]:
            continue
        rest = iter(text[start + 1 : start + window])
        if all(any(t == w for t in rest) for w in wanted[1:]):
            return True
    return False


# ---- numbers in the student's words, for code's consistency checks ----

_VALUE = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
_OPERAND = r"[$€£]?\s*-?\d+(?:,\d{3})*(?:\.\d+)?"
_EQUATION = re.compile(rf"((?:{_OPERAND})(?:\s*[-+−–×x*÷/]\s*{_OPERAND})+)\s*=\s*({_OPERAND})(?!\s*%)")
_OPERATORS = str.maketrans({"−": "-", "–": "-", "×": "*", "x": "*", "÷": "/"})


def numeric_values(text: str) -> set[float]:
    """Every number written in a text (currency signs, percent signs and thousands commas ignored)."""
    found = set()
    for token in _VALUE.findall(text):
        try:
            found.add(round(float(token.replace(",", "")), 6))
        except ValueError:
            continue
    return found


_PERCENT = re.compile(
    rf"(\d+(?:\.\d+)?)\s*%\s*of\s+(?:[^\d=.;]{{0,30}}?)({_OPERAND})\s*(?:[^\W\d_]{{1,12}}\s*)?(?:is|=|equals|gives)\s*"
    rf"({_OPERAND})", re.I
)


class Calculation(NamedTuple):
    """One calculation the student wrote: the numbers it uses, the result it claims, and whether that is true."""

    operands: frozenset[float]
    result: float
    holds: bool
    at: int = 0  # where it starts in the text


def _number(text: str) -> float:
    return float(re.sub(r"[$€£,\s]", "", text))


def calculations(text: str) -> list[Calculation]:
    """Every plain calculation written in the text: "a op b (op c) = r" and "p% of N is r"."""
    found = []
    for match in _EQUATION.finditer(text):
        left, right = match.groups()
        expression = re.sub(r"[$€£,\s]", "", left).translate(_OPERATORS)
        if not re.fullmatch(r"[-+*/.\d]+", expression):
            continue
        try:
            value = eval(expression, {"__builtins__": {}}, {})  # digits and + - * / only (checked above)
            holds = abs(value - _number(right)) <= 0.005 + 1e-9 * abs(value)
        except (ArithmeticError, SyntaxError):
            holds = False
        operands = frozenset(abs(v) for v in numeric_values(left))
        found.append(Calculation(operands, round(_number(right), 6), holds, match.start()))
    for match in _PERCENT.finditer(text):
        percent, base, right = match.groups()
        value = float(percent) / 100 * _number(base)
        found.append(Calculation(frozenset({float(percent), _number(base)}), round(_number(right), 6),
                                 abs(value - _number(right)) <= 0.005 + 1e-9 * abs(value), match.start()))
    return found


def arithmetic_holds(text: str) -> bool:
    """Whether every plain calculation written in the text is true (none written: nothing to fail)."""
    return all(c.holds for c in calculations(text))
