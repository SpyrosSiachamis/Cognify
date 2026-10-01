"""Small helpers for reading the student's own words, shared by the reasoning rules and repair."""

import re

# Saying you do not know how to do a step is missing evidence (English only for now).
NOT_KNOWING = re.compile(r"\b(i )?(do not|don't|dont) know\b|\bnot sure\b|\bno idea\b|\bi'?m stuck\b|\bcan'?t (figure|work) out\b", re.I)


def substantive(quote: str | None) -> bool:
    """Whether a quote says something beyond not knowing ("I don't know" alone is not evidence)."""
    if not quote:
        return False
    rest = NOT_KNOWING.sub(" ", normalise(quote))
    return len(re.findall(r"[\w.^/=+-]+", rest)) >= 4


def normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip(" .,;:!?\"'")
