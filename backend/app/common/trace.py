"""The development session trace: typed events recorded where they happen, kept per request.

The session service opens a buffer for each call it serves (start, attempt, exit) and saves it through
app/history when the call ends, so any module can record an event without being handed the session. Nothing here
stores anything or changes behaviour: with no open buffer (tracing off, or a call outside a session) record() does
nothing, and a payload that fails validation is logged and dropped, never raised into the tutoring path.

Development instrumentation only (DEBUG_TRACE=true). It keeps the student's text and every draft, because those
are what a rejection has to be debugged from; it never keeps credentials, headers or account data. It records
what the runtime knows (for example "verifier rejected: method_drift"), never a judgement of whose fault that was:
that analysis is done later, by people reading the trace.

Categorical fields use the shared glossary (vocab); free text (notes, drafts, messages) is supplementary.
"""

import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_core import to_jsonable_python

from app.common.vocab import (
    AttemptKind,
    Confidence,
    DecisionMode,
    Difficulty,
    Evidence,
    GapType,
    GatewayFailure,
    ModelCallOutcome,
    ModelOperation,
    NotYetReason,
    Perturbation,
    Phase,
    RejectionReason,
    ReplyOutcome,
    ResolutionState,
    ResponseTo,
    SessionStatus,
    State,
    Strategy,
    TraceOperation,
)

log = logging.getLogger(__name__)

TeachMode = Literal["teach", "probe", "acknowledge"]


def enabled() -> bool:
    return os.environ.get("DEBUG_TRACE", "false").strip().lower() == "true"


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Counters(_Payload):
    """The session's own counters at that moment (unchanged by tracing)."""

    hints_used: int
    hint_owed: bool  # the last reply was a delivered teaching move: the next answer counts one hint
    teach_turns: int
    not_yet_count: int
    transfer_attempts: int  # answers to a fresh problem so far
    drafts: int  # teaching drafts so far
    verifier_rejections: int  # of those, rejected by the verifier


class SessionStarted(_Payload):
    event_type: Literal["SESSION_STARTED"] = "SESSION_STARTED"
    student_id: UUID
    problem_id: UUID
    problem: str
    subject: str | None
    concept_id: UUID
    concept_name: str
    concept_state: State  # the learner's state of this concept at the start
    phase: Phase
    force_experiment: bool
    solution_result: str  # the hidden solution's result (backend only, as the session keeps it)


class StudentResponse(_Payload):
    event_type: Literal["STUDENT_RESPONSE"] = "STUDENT_RESPONSE"
    text: str
    kind: AttemptKind  # what the backend expects it to be, from the phase
    blank: bool
    phase: Phase
    problem_id: UUID
    practice_follow_up_id: UUID | None  # set when the repair cycle works on a failed fresh problem
    problem: str  # the problem the answer is read against
    tutor_message: str | None  # the reply it answers (the context the diagnosis gets)
    concept_state: State
    counters: Counters


class ModelCall(_Payload):
    event_type: Literal["MODEL_CALL"] = "MODEL_CALL"
    operation: ModelOperation
    provider: str  # the model library's system name, e.g. "bedrock"
    model: str
    outcome: ModelCallOutcome
    latency_ms: int
    requests: int | None = None  # model requests in the call; more than one means output-validation retries
    input_tokens: int | None = None
    output_tokens: int | None = None
    http_status: int | None = None
    provider_error_code: str | None = None  # e.g. ServiceUnavailableException
    provider_error_message: str | None = None
    request_id: str | None = None
    sdk_retry_attempts: int | None = None  # retries the AWS SDK already made before giving up
    transient: bool | None = None  # 429 or 5xx: a service-availability condition, not a bad reply
    timeout_seconds: float | None = None
    detail: str | None = None


class ReasoningRead(_Payload):
    """What the diagnosis model received and what it proposed, before code's rules."""

    event_type: Literal["REASONING_READ"] = "REASONING_READ"
    problem: str
    attempt: str
    final_answer: str | None
    tutor_message: str | None
    # Passed forward for code's rules only (never sent to the model): values the problem's working really reaches,
    # from its worked solution and from results the student already showed correctly in this cycle.
    reached_values: list[float] = []
    outcome: Literal["ok"] | GatewayFailure
    proposal: dict[str, Any] | None  # the model's raw reading
    detail: str | None = None


class DiagnosisResult(_Payload):
    """The diagnosis exactly as the teaching stage received it, and the code decisions made from it."""

    event_type: Literal["DIAGNOSIS_RESULT"] = "DIAGNOSIS_RESULT"
    kind: Literal["initial", "repair", "follow_up"]  # first thought; a gap being taught; any later answer
    main_gap: GapType | None
    alternatives: list[GapType]
    confidence: Confidence
    evidence: Evidence
    response_to: ResponseTo
    diagnosis_failed: GatewayFailure | None  # the reasoning call failed: the insufficient-evidence fallback
    prior_gap: GapType | None
    gap_carried: bool  # main_gap is the gap still being taught, not one this answer showed
    gap_repaired: bool
    repair_reason: str
    # The student's correction proved the challenged step (code's correct-work resolution), and the values it rests on.
    resolved_by_correct_work: bool = False
    validated_values: list[float] = []
    # Code's reading of where the student stands (only PROBLEM_RESOLVED removes support), the values their own work has
    # demonstrated in this cycle, and the first worked-solution step not yet demonstrated.
    resolution_state: ResolutionState = "CURRENT_TARGET_UNRESOLVED"
    demonstrated_values: list[float] = []
    current_target: str | None = None
    mode: TeachMode
    gap_step: dict[str, Any] | None
    method: Strategy | None
    decision_mode: DecisionMode | None
    strategy_reason: str | None
    strategy_uses: int | None  # the learner's record for this gap and method, as choose_strategy read it
    strategy_independent_successes: int | None
    diagnosis: dict[str, Any]  # the full TutorDiagnosis passed downstream


class TeachingGenerationStarted(_Payload):
    event_type: Literal["TEACHING_GENERATION_STARTED"] = "TEACHING_GENERATION_STARTED"
    attempt: int
    mode: Literal["teach", "probe"]
    method: Strategy | None
    main_gap: GapType | None
    gap_step: dict[str, Any] | None
    retry_reason: RejectionReason | None  # why the previous draft was rejected, passed back to the writer
    retry_note: str | None
    language: str
    hints_used: int
    problem: str


class TeachingGenerationResult(_Payload):
    event_type: Literal["TEACHING_GENERATION_RESULT"] = "TEACHING_GENERATION_RESULT"
    attempt: int
    outcome: Literal["draft", "teaching_failed", "wrong_language"]
    draft: str | None
    failure: GatewayFailure | None
    detail: str | None = None
    model: str


class VerifierResult(_Payload):
    event_type: Literal["VERIFIER_RESULT"] = "VERIFIER_RESULT"
    attempt: int
    checker: Literal["code_leak_check", "model"]  # the code check runs first and needs no model call
    outcome: Literal["approved", "verifier_rejected", "verifier_error"]
    reason: RejectionReason | None  # the verifier's own category; nothing is inferred beyond it
    note: str
    method: Strategy | None
    main_gap: GapType | None
    gap_step: str | None  # as the verifier read it
    draft: str
    student_demonstrated: list[str]
    withheld_answers: list[str]  # final answers the code leak check looked for


class FallbackDraft(_Payload):
    attempt: int
    outcome: ReplyOutcome
    reason: RejectionReason | None
    note: str
    draft: str | None


class TeachingFallback(_Payload):
    event_type: Literal["TEACHING_FALLBACK"] = "TEACHING_FALLBACK"
    attempts: int
    last_outcome: ReplyOutcome
    last_reason: RejectionReason | None
    drafts: list[FallbackDraft]
    fallback_reply: str
    explanation: str  # what the reply explains (tutor/fallback.py FallbackKind)
    # The student sent working the diagnosis could not place on this problem's steps: a matching problem to look at,
    # not missing evidence.
    evidence_unrecognized: bool
    main_gap: GapType | None
    method: Strategy | None
    counts_as_hint: bool  # a fallback never does (F16); whether it was shown is in REPLY_SENT


class ReplySent(_Payload):
    """What the turn sent back, and what it means for the hint count and the next answer's context."""

    event_type: Literal["REPLY_SENT"] = "REPLY_SENT"
    kind: Literal["teaching", "probe", "acknowledgement", "safe_fallback", "turn_failed", "blank_prompt",
                  "fresh_problem", "verdict"]
    message: str
    reply_outcome: ReplyOutcome | None
    method: Strategy | None
    shown_to_student: bool
    counts_as_hint: bool  # one hint is counted on the student's next answer
    # Set when a long unresolved cycle offered the student the choice to stop (never a move to a fresh problem).
    unresolved_policy: Literal["offer_exit"] | None = None


class StateTransition(_Payload):
    event_type: Literal["STATE_TRANSITION"] = "STATE_TRANSITION"
    previous_phase: Phase
    trigger: Literal["first_answer", "problem_resolved", "gap_repaired", "no_gap", "turn_cap", "verified", "not_yet",
                     "not_yet_final", "exit"]  # gap_repaired, no_gap and turn_cap are no longer emitted
    new_phase: Phase
    status: SessionStatus
    practice_follow_up_id: UUID | None
    counters: Counters


class SupportRemoved(_Payload):
    event_type: Literal["SUPPORT_REMOVED"] = "SUPPORT_REMOVED"
    reason: Literal["problem_resolved", "gap_repaired", "no_gap", "turn_cap"]  # only problem_resolved is emitted now
    problem_id: UUID
    practice_follow_up_id: UUID | None  # the practice problem whose repair cycle just ended, if any
    main_gap: GapType | None
    method: Strategy | None  # the last teaching move delivered in this cycle, if any
    concept_state: State
    replaced_reply: str | None  # this turn's reply, which the student never saw: the fresh problem replaced it
    counters: Counters


class FollowUpStarted(_Payload):
    event_type: Literal["FOLLOW_UP_STARTED"] = "FOLLOW_UP_STARTED"
    request: int  # the session's request for a follow-up (a repeated problem is asked for again)
    reason: Literal["support_removed"]
    retry_reason: str | None
    problem_id: UUID
    main_gap: GapType | None
    method: Strategy | None
    hints_used: int
    last_steps: list[dict[str, Any]]


class FollowUpResult(_Payload):
    event_type: Literal["FOLLOW_UP_RESULT"] = "FOLLOW_UP_RESULT"
    attempt: int  # 0 for the session's freshness check
    outcome: Literal["approved", "rejected_by_code", "rejected_by_verifier", "generation_failed", "verifier_failed",
                     "already_seen"]
    reason: RejectionReason | None = None
    note: str | None = None
    failure: GatewayFailure | None = None
    detail: str | None = None
    draft: dict[str, Any] | None = None


class FreshProblemGenerated(_Payload):
    event_type: Literal["FRESH_PROBLEM_GENERATED"] = "FRESH_PROBLEM_GENERATED"
    follow_up_id: UUID
    problem_id: UUID  # the original problem
    problem: str
    concept_invariant: str
    target_gap: GapType
    target_step: str
    perturbation: Perturbation
    difficulty: Difficulty
    fingerprint: str
    support_removed: bool
    hints_available: bool


class TransferResult(_Payload):
    event_type: Literal["TRANSFER_RESULT"] = "TRANSFER_RESULT"
    problem_id: UUID
    follow_up_id: UUID
    problem: str
    fresh_problem: str
    concept_id: UUID
    concept_name: str
    support_removed: bool
    hints_used: int
    student_text: str
    correct: bool
    own_work: bool
    reasoning_quality: str
    judge_note: str
    verified: bool
    independent: bool
    not_yet_reason: NotYetReason | None
    concept_before: State
    concept_after: State
    gap_credited: GapType | None
    method_credited: Strategy | None
    decision_mode: DecisionMode | None
    strategy_uses_before: int | None
    strategy_independent_successes_before: int | None
    strategy_uses_after: int | None
    strategy_independent_successes_after: int | None
    session_over: bool
    practice_follow_up_id: UUID | None  # the repair cycle that follows a first NOT YET works on this problem


class JudgeConsistencyCheck(_Payload):
    """The judge called a fresh-problem answer incorrect; code checked whether the student's own work holds."""

    event_type: Literal["JUDGE_CONSISTENCY_CHECK"] = "JUDGE_CONSISTENCY_CHECK"
    judge_correct: bool
    judge_note: str
    consistent: bool
    reasons: list[str]  # why the work is not consistent (empty when it is)
    overridden: bool  # the verdict was changed to correct (the student's consistent work outweighs the rubric)


class SessionError(_Payload):
    event_type: Literal["SESSION_ERROR"] = "SESSION_ERROR"
    operation: TraceOperation
    handled: bool  # True: a fallback was sent and the turn went on; False: the call failed
    error_type: str
    message: str
    api_status: int | None
    api_code: str | None
    causes: list[dict[str, str]]  # the exceptions behind it, outermost first


class SessionEnded(_Payload):
    event_type: Literal["SESSION_ENDED"] = "SESSION_ENDED"
    reason: Literal["verified", "not_yet_cap", "exit"]
    status: SessionStatus
    phase: Phase
    verified: bool
    transfer_attempts: int
    transfer_succeeded: bool
    duration_seconds: float
    counters: Counters


TracePayload = Annotated[
    Union[
        SessionStarted, StudentResponse, ModelCall, ReasoningRead, DiagnosisResult, TeachingGenerationStarted,
        TeachingGenerationResult, VerifierResult, TeachingFallback, ReplySent, StateTransition, SupportRemoved,
        FollowUpStarted, FollowUpResult, FreshProblemGenerated, TransferResult, JudgeConsistencyCheck, SessionError,
        SessionEnded,
    ],
    Field(discriminator="event_type"),
]


# ---- the per-call buffer ----


@dataclass
class Pending:
    """An event recorded during a call, before the session it belongs to is saved."""

    at: datetime
    payload: _Payload


@dataclass
class Buffer:
    events: list[Pending] = field(default_factory=list)
    # Errors already recorded where they happened, so the call's own handler does not record them twice.
    recorded_errors: set[int] = field(default_factory=set)


_current: ContextVar[Buffer | None] = ContextVar("session_trace", default=None)


@contextmanager
def collecting(on: bool = True) -> Iterator[Buffer | None]:
    """Collect the events of one call. Tasks started inside it (asyncio.wait_for) share the same buffer."""
    if not on:
        yield None
        return
    buffer = Buffer()
    token = _current.set(buffer)
    try:
        yield buffer
    finally:
        _current.reset(token)


def active() -> bool:
    return _current.get() is not None


@contextmanager
def guard() -> Iterator[None]:
    """Around code that only builds trace events: a mistake there is logged, never raised into the turn."""
    try:
        yield
    except Exception:
        log.error("trace: an event was not recorded", exc_info=True)


def record(payload_type: type[_Payload], **fields: Any) -> None:
    """Record one event. Fields may be Pydantic models (dumped as JSON). Never raises."""
    buffer = _current.get()
    if buffer is None:
        return
    try:
        payload = payload_type.model_validate(_scrub(to_jsonable_python(fields, fallback=repr)))
    except (ValidationError, TypeError, ValueError):
        log.error("trace: dropped an invalid %s event", payload_type.__name__, exc_info=True)
        return
    buffer.events.append(Pending(datetime.now(UTC), payload))


def record_error(
    operation: TraceOperation, error: BaseException, handled: bool = False, cause: BaseException | None = None
) -> None:
    """A SESSION_ERROR, with the exceptions behind it (cause: the one it is about to be raised from)."""
    buffer = _current.get()
    if buffer is None:
        return
    buffer.recorded_errors.add(id(error))
    status = getattr(error, "status", None)
    body = getattr(error, "body", None)
    record(
        SessionError,
        operation=operation,
        handled=handled,
        error_type=type(error).__name__,
        message=str(error)[:2000],
        api_status=status if isinstance(status, int) else None,
        api_code=getattr(body, "code", None),
        causes=cause_chain(cause or error.__cause__ or error.__context__),
    )


# Provider error bodies carry the response headers ('HTTPHeaders': {...}); the trace keeps the structured fields
# (status, error code, request id) and never the headers.
_HEADERS = re.compile(r",?\s*['\"]HTTPHeaders['\"]\s*:\s*\{[^{}]*\}")
_SECRET_NAMES = ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")


def _secrets() -> list[str]:
    return [v for k, v in os.environ.items() if len(v) >= 8 and any(n in k.upper() for n in _SECRET_NAMES)]


def _scrub(value: Any, secrets: list[str] | None = None) -> Any:
    """Headers and any configured secret are cut from every string before an event is kept."""
    secrets = _secrets() if secrets is None else secrets
    if isinstance(value, str):
        value = _HEADERS.sub("", value)
        for secret in secrets:
            value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, dict):
        return {k: _scrub(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, secrets) for v in value]
    return value


def already_recorded(error: BaseException) -> bool:
    buffer = _current.get()
    return buffer is not None and id(error) in buffer.recorded_errors


def cause_chain(error: BaseException | None) -> list[dict[str, str]]:
    """Each exception behind an error, outermost first: its type and message."""
    chain: list[dict[str, str]] = []
    while error is not None and len(chain) < 5:
        chain.append({"type": type(error).__name__, "message": str(error)[:2000]})
        error = error.__cause__ or error.__context__
    return chain
