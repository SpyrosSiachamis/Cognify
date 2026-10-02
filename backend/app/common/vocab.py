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

# Whether an attempt holds enough reasoning to diagnose; insufficient means ask a probe.
Evidence = Literal["sufficient", "insufficient"]

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

# Why a stress-test answer was NOT YET (decided by code in the session flow, F16). Only incorrect and
# not_own_work are evidence that the student could not do it; hint_limit is about the help they needed.
NotYetReason = Literal["incorrect", "not_own_work", "hint_limit"]

# What a student message answers, read in the context of the tutor's last delivered message.
# Only original_problem is read as work on the problem as a whole.
ResponseTo = Literal["original_problem", "tutor_question", "other_problem", "clarification", "acknowledgement"]

# How a reply came to be what the student saw (telemetry; the per-draft detail is kept in history).
ReplyOutcome = Literal[
    "approved",  # a checked reply the verifier approved
    "fixed_reply",  # a fixed text that needs no check (an acknowledgement, the blank-text question)
    "verifier_rejected",  # every draft was rejected by the verifier; safe fallback sent
    "teaching_failed",  # the teaching step returned no usable draft (timeout, invalid output, provider error)
    "verifier_error",  # the verifier call itself failed, so the draft was not sent
    "wrong_language",  # every draft came back in the wrong language
    "turn_failed",  # the whole turn failed in the session flow; safe fallback sent
]

VerifierMode = Literal["reply_check", "follow_up_check", "student_check"]

RejectionReason = Literal[
    "answer_leak",
    "heavy_hint",
    "method_drift",
    "off_target",
    "shaming_tone",
    "invalid_followup",
    "not_independent",
]

# How the session ended (docs/ARCHITECTURE.md: verified, ended after the NOT YET cap, or exited).
# Must match the sessions.status check in supabase/migrations/0001_init.sql.
SessionStatus = Literal["active", "verified", "not_yet_ended", "exited"]

# What a student message is, decided by the backend from session state (API_CONTRACT).
AttemptKind = Literal["first_thought", "teaching_reply", "follow_up_attempt"]

# Why a gateway call fell back (docs/ARCHITECTURE.md, caps and fallbacks).
GatewayFailure = Literal["invalid_output", "timeout", "provider_error"]

# One event of the development session trace (docs/DATA.md, session trace). Debugging only; never shown to students.
TraceEventType = Literal[
    "SESSION_STARTED",
    "STUDENT_RESPONSE",
    "MODEL_CALL",
    "REASONING_READ",
    "DIAGNOSIS_RESULT",
    "TEACHING_GENERATION_STARTED",
    "TEACHING_GENERATION_RESULT",
    "VERIFIER_RESULT",
    "TEACHING_FALLBACK",
    "REPLY_SENT",
    "STATE_TRANSITION",
    "SUPPORT_REMOVED",
    "FOLLOW_UP_STARTED",
    "FOLLOW_UP_RESULT",
    "FRESH_PROBLEM_GENERATED",
    "TRANSFER_RESULT",
    "SESSION_ERROR",
    "SESSION_ENDED",
]

# How a model call ended, as the trace tells them apart (a provider outage is not a bad reply).
# cancelled: the session's own turn time limit stopped the call while it was still waiting on the model.
ModelCallOutcome = Literal[
    "ok", "provider_http_error", "provider_connection_error", "timeout", "invalid_output", "cancelled"
]

# Which model call it was: the name of the agent that made it (one per stage).
ModelOperation = Literal[
    "tutor_setup", "tutor_reasoning", "tutor_teaching", "tutor_follow_up",
    "reply_checker", "follow_up_checker", "student_checker",
]

# What a session call was doing when it failed (SESSION_ERROR).
TraceOperation = Literal["start", "teach", "follow_up", "judge", "practice_set_up", "attempt", "exit"]


def values(vocab_type: object) -> tuple[str, ...]:
    """The allowed strings of a vocabulary type, e.g. for a SQL CHECK constraint."""
    return get_args(vocab_type)
