"""The student's language, decided by code (docs/PROMPTS.md: English or Greek).

The teaching step is told the language explicitly, and a draft in another
language is regenerated before the verifier or the student sees it.
"""

import re
from typing import Literal

Language = Literal["English", "Greek"]

GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
LATIN = re.compile(r"[a-zA-Z]")
WORD = re.compile(r"[a-zà-ÿ']+")
ENGLISH = {
    "the", "a", "an", "is", "are", "i", "you", "it", "to", "of", "and", "or", "in", "on", "at", "what",
    "how", "why", "which", "do", "does", "can", "could", "would", "your", "this", "that", "for", "with",
    "know", "think", "if", "be", "was", "not", "as", "so", "now", "let's", "look", "find", "there",
}
# Common function words of other Latin-script languages the model drifts into.
OTHER = {
    "le", "la", "les", "est", "tu", "vous", "pour", "une", "des", "du", "que", "qui", "et", "avec", "au",
    "el", "los", "las", "es", "por", "para", "una", "qué", "der", "die", "das", "und", "ist", "nicht",
    "il", "che", "per", "sono", "um", "uma", "não", "como",
}


def student_language(text: str) -> Language:
    """Greek script means Greek; anything else is English (the two supported languages)."""
    return "Greek" if len(GREEK.findall(text)) > len(LATIN.findall(text)) else "English"


def written_in(text: str, language: Language) -> bool:
    """Whether a reply is in the expected language."""
    if language == "Greek":
        return len(GREEK.findall(text)) > len(LATIN.findall(text))
    if len(GREEK.findall(text)) > len(LATIN.findall(text)):
        return False
    words = WORD.findall(text.lower())
    return sum(w in ENGLISH for w in words) >= sum(w in OTHER for w in words)


FALLBACK_REPLY: dict[Language, str] = {
    "English": "Let's slow down for a moment. Which step of your answer are you least sure about, and why?",
    "Greek": "Ας το πάρουμε λίγο πιο αργά. Ποιο βήμα της απάντησής σου σου φαίνεται πιο δύσκολο, και γιατί;",
}
ACKNOWLEDGE_REPLY: dict[Language, str] = {
    "English": "Every step holds up. Next comes a fresh problem to try on your own.",
    "Greek": "Όλα τα βήματα στέκουν. Ακολουθεί ένα νέο πρόβλημα για να το δοκιμάσεις χωρίς βοήθεια.",
}
