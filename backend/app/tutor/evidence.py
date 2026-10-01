"""Small helpers for reading the student's own words, shared by the reasoning rules and repair."""

import re

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
