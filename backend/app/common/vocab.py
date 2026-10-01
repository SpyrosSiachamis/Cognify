"""The shared vocabulary: every glossary value from docs/API_CONTRACT.md, defined once.

API schemas, AI output models, history records and (later) SQL CHECK
constraints import these types. Do not retype a glossary string anywhere else.
"""

from typing import Literal, get_args

Phase = Literal["ask_first_thought", "teach", "stress_test", "verdict", "exited"]

GapType = Literal[
    "recognition",
    "representation",
    "concept",
    "procedure",
    "strategy_choice",
    "self_correction",
    "transfer",
]

Strategy = Literal[
    "socratic",
    "visual_decomposition",
    "worked_example",
    "analogy",
    "counterexample",
    "representation_switch",
    "micro_hint",
]

DecisionMode = Literal["best_known", "experiment", "cold_start"]

StepRole = Literal[
    "identify_quantities", "choose_method", "set_up", "substitute", "compute", "interpret"
]

StepStatus = Literal["correct", "wrong", "missing"]

# Ratings for a dimension; a concept state is a rating or "verified".
Rating = Literal["strong", "fragile", "weak", "untested"]
State = Literal["strong", "fragile", "weak", "untested", "verified"]

Confidence = Literal["low", "medium", "high"]

# The nine reasoning dimensions (SPEC F8).
Dimension = Literal[
    "correctness",
    "recognition",
    "representation",
    "concept",
    "procedure",
    "strategy_choice",
    "self_correction",
    "hint_dependency",
    "transfer",
]

# What a follow-up problem changes (SPEC F15).
Perturbation = Literal["wording", "representation", "context", "distractors"]

Difficulty = Literal["easy", "medium", "hard"]

VerdictResult = Literal["VERIFIED", "NOT YET"]

VerifierMode = Literal["reply_check", "follow_up_check", "student_check"]

RejectionReason = Literal[
    "answer_leak",
    "heavy_hint",
    "method_drift",
    "shaming_tone",
    "invalid_followup",
    "not_independent",
]


def values(vocab_type: object) -> tuple[str, ...]:
    """The allowed strings of a vocabulary type, e.g. for a SQL CHECK constraint."""
    return get_args(vocab_type)
