"""Records the app remembers (docs/DATA.md). One flat model per record kind.

No column or table definitions live in the docs; these models are the shape the
database will copy. IDs are UUID v4 and foreign keys are plain UUID fields.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    UUID4,
    computed_field,
    model_validator,
)

from app.common.trace import TracePayload
from app.common.vocab import (
    Confidence,
    DecisionMode,
    Difficulty,
    Dimension,
    GapType,
    Perturbation,
    Phase,
    NotYetReason,
    Rating,
    RejectionReason,
    ReplyOutcome,
    ResponseTo,
    SessionStatus,
    State,
    StepRole,
    StepStatus,
    Strategy,
    TraceEventType,
    VerdictResult,
    VerifierMode,
)

Text = Annotated[str, Field(min_length=1)]


def now() -> datetime:
    return datetime.now().astimezone()


class Record(BaseModel):
    """Strict base: an unknown field or a bad value fails instead of being stored."""

    model_config = ConfigDict(extra="forbid")


class Student(Record):
    id: UUID4 = Field(default_factory=uuid4)
    display_name: Text
    is_seeded: bool = False
    created_at: AwareDatetime = Field(default_factory=now)


class Concept(Record):
    id: UUID4 = Field(default_factory=uuid4)
    name: Text


class Problem(Record):
    id: UUID4 = Field(default_factory=uuid4)
    text: Text
    subject: str | None = None
    fingerprint: Text
    created_at: AwareDatetime = Field(default_factory=now)


class SessionSolution(Record):
    """The hidden worked solution. Backend only; it leaves only through an explicit exit."""

    result: Text
    steps: list[Text] = Field(min_length=1)


class PracticeProblem(Record):
    """The fresh problem a first NOT YET was given on, with its own hidden solution. It is the problem of the
    repair cycle that follows; the session's own problem (problem_id) stays the original."""

    follow_up_id: UUID4
    text: Text
    solution: SessionSolution


class Session(Record):
    id: UUID4 = Field(default_factory=uuid4)
    student_id: UUID4
    problem_id: UUID4
    concept_id: UUID4 | None = None
    phase: Phase = "ask_first_thought"
    status: SessionStatus = "active"
    hints_used: int = Field(default=0, ge=0)
    teach_turns: int = Field(default=0, ge=0)  # since the session started or the last NOT YET
    not_yet_count: int = Field(default=0, ge=0)
    force_experiment: bool = False  # the demo flag from the start request
    # Whether the last reply was an approved teaching move that reached the student. Only then does the next
    # attempt count one hint (F16): fallbacks, probes and acknowledgements are not help.
    last_reply_taught: bool = False
    # The last tutor reply the student saw (a teaching move, a probe, a fallback, or after a NOT YET the verdict), so
    # the next answer is read in context. Separate from hint counting (last_reply_taught). None when the next
    # answer is to be read as work on the problem itself (the first thought, and the fresh problem).
    last_tutor_message: str | None = None
    hidden_solution: SessionSolution | None = None
    # Set by a first NOT YET: the failed fresh problem the repair cycle teaches on; cleared when that cycle ends
    # with a new fresh problem. History, learner state and exit always use problem_id and hidden_solution.
    active_practice_problem: PracticeProblem | None = None
    started_at: AwareDatetime = Field(default_factory=now)
    ended_at: AwareDatetime | None = None


class Attempt(Record):
    id: UUID4 = Field(default_factory=uuid4)
    session_id: UUID4
    phase: Phase
    text: Text
    response_to: ResponseTo = "original_problem"  # what the message answered (the reasoning step's reading)
    created_at: AwareDatetime = Field(default_factory=now)


class AttemptStep(Record):
    id: UUID4 = Field(default_factory=uuid4)
    attempt_id: UUID4
    position: int = Field(ge=0)
    role: StepRole
    status: StepStatus
    quote: str | None = None

    @model_validator(mode="after")
    def quote_unless_missing(self) -> "AttemptStep":
        if self.status != "missing" and not self.quote:
            raise ValueError("a correct or wrong step must quote the student's words")
        return self


class AlternativeGap(Record):
    gap: GapType
    confidence: Confidence


class DimensionRating(Record):
    name: Dimension
    state: Rating
    evidence: Text


class Diagnosis(Record):
    id: UUID4 = Field(default_factory=uuid4)
    attempt_id: UUID4
    main_gap: GapType | None = None  # None: no gap demonstrated, or not enough evidence yet
    alternatives: list[AlternativeGap] = []
    confidence: Confidence
    dimensions: list[DimensionRating] = []
    created_at: AwareDatetime = Field(default_factory=now)

    @model_validator(mode="after")
    def main_gap_not_in_alternatives(self) -> "Diagnosis":
        if any(alt.gap == self.main_gap for alt in self.alternatives):
            raise ValueError("the main gap must not also appear in alternatives")
        return self


class StrategyDecision(Record):
    id: UUID4 = Field(default_factory=uuid4)
    session_id: UUID4
    gap_type: GapType
    method: Strategy
    decision_mode: DecisionMode
    reason: Text
    uses: int = Field(ge=0)
    independent_successes: int = Field(ge=0)
    created_at: AwareDatetime = Field(default_factory=now)


class FollowUp(Record):
    id: UUID4 = Field(default_factory=uuid4)
    session_id: UUID4
    problem_text: Text
    fingerprint: Text
    concept_invariant: Text
    target_gap: GapType
    target_step: StepRole
    perturbation: Perturbation
    difficulty: Difficulty
    hidden_rubric: list[Text]
    created_at: AwareDatetime = Field(default_factory=now)

    @model_validator(mode="after")
    def rubric_not_empty(self) -> "FollowUp":
        if not self.hidden_rubric:
            raise ValueError("hidden_rubric needs at least one item")
        return self


class ReplyDraft(Record):
    """One teaching draft of a turn and what became of it (debugging and telemetry; never shown to students)."""

    id: UUID4 = Field(default_factory=uuid4)
    session_id: UUID4
    attempt_id: UUID4 | None = None
    position: int = Field(ge=0)
    outcome: ReplyOutcome  # approved, verifier_rejected, teaching_failed, verifier_error or wrong_language
    reason: RejectionReason | None = None  # the verifier's reason, only for verifier_rejected
    note: str = ""  # the verifier's note, or the failure detail
    method: Strategy | None = None  # the method the draft was written for, if any
    created_at: AwareDatetime = Field(default_factory=now)

    @model_validator(mode="after")
    def reason_only_for_rejection(self) -> "ReplyDraft":
        if (self.outcome == "verifier_rejected") != (self.reason is not None):
            raise ValueError("a rejection reason is set exactly when the verifier rejected the draft")
        if self.outcome in ("fixed_reply", "turn_failed"):
            raise ValueError("fixed replies and failed turns are not drafts")
        return self


class TraceEvent(Record):
    """One event of the development session trace: what each stage received, produced and decided, in order.

    Debugging only (never shown to students, never read by the tutor), kept only when tracing is on
    (DEBUG_TRACE). The store numbers a session's events (sequence) and the service calls that produced them (turn).
    """

    id: UUID4 = Field(default_factory=uuid4)  # the event id
    session_id: UUID4
    sequence: int = Field(default=0, ge=0)
    turn: int = Field(default=0, ge=0)  # 0 is the session start; then one per attempt or exit call
    at: AwareDatetime = Field(default_factory=now)
    payload: TracePayload  # typed per event type (app/common/trace.py)

    @computed_field
    @property
    def event_type(self) -> TraceEventType:
        return self.payload.event_type


class VerifierCheck(Record):
    id: UUID4 = Field(default_factory=uuid4)
    session_id: UUID4
    mode: VerifierMode
    approved: bool
    reason: RejectionReason | None = None
    note: Text
    # Only for the student check.
    correct: bool | None = None
    reasoning_quality: Rating | None = None
    own_work: bool | None = None
    created_at: AwareDatetime = Field(default_factory=now)

    @model_validator(mode="after")
    def reason_matches_approval(self) -> "VerifierCheck":
        if self.approved and self.reason is not None:
            raise ValueError("an approved check must not have a rejection reason")
        if not self.approved and self.reason is None:
            raise ValueError("a rejected check needs a rejection reason")
        return self

    @model_validator(mode="after")
    def student_check_fields(self) -> "VerifierCheck":
        if self.mode == "student_check" and None in (
            self.correct,
            self.reasoning_quality,
            self.own_work,
        ):
            raise ValueError("a student check needs correct, reasoning_quality and own_work")
        return self


class Outcome(Record):
    id: UUID4 = Field(default_factory=uuid4)
    student_id: UUID4
    session_id: UUID4 | None = None
    concept_id: UUID4
    # None when the session taught nothing (right from the start); no method gets credit.
    gap_type: GapType | None = None
    method: Strategy | None = None
    decision_mode: DecisionMode | None = None
    result: VerdictResult
    # Why a NOT YET (None for VERIFIED). Seeded rows may leave it unset.
    not_yet_reason: NotYetReason | None = None
    independent: bool
    hints_used: int = Field(ge=0)
    concept_before: State
    concept_after: State
    evidence: Text
    remaining_gap: GapType | None = None
    is_seeded: bool = False
    created_at: AwareDatetime = Field(default_factory=now)

    @model_validator(mode="after")
    def verified_needs_independence(self) -> "Outcome":
        if self.result == "VERIFIED" and not self.independent:
            raise ValueError("VERIFIED requires independent=True (a lucky answer is NOT YET)")
        return self

    @model_validator(mode="after")
    def method_fields_together(self) -> "Outcome":
        if len({self.gap_type is None, self.method is None, self.decision_mode is None}) > 1:
            raise ValueError("gap_type, method and decision_mode are all set or all None")
        return self

    @model_validator(mode="after")
    def only_seeded_without_session(self) -> "Outcome":
        if self.session_id is None and not self.is_seeded:
            raise ValueError("session_id may be None only for a seeded outcome")
        return self

    @model_validator(mode="after")
    def verified_state_needs_verified_result(self) -> "Outcome":
        # A NOT YET may leave an already verified concept verified only when the student did solve the fresh
        # problem correctly on their own (hint_limit): that is not evidence they lost it.
        keeps_verified = self.concept_before == "verified" and self.not_yet_reason == "hint_limit"
        if self.concept_after == "verified" and self.result != "VERIFIED" and not keeps_verified:
            raise ValueError("a concept becomes verified only on a VERIFIED result")
        return self

    @model_validator(mode="after")
    def not_yet_reason_matches_result(self) -> "Outcome":
        if self.result == "VERIFIED" and self.not_yet_reason is not None:
            raise ValueError("a VERIFIED outcome has no NOT YET reason")
        if self.result == "NOT YET" and self.not_yet_reason is None and not self.is_seeded:
            raise ValueError("a NOT YET outcome needs a reason")
        return self


class ConceptState(Record):
    student_id: UUID4
    concept_id: UUID4
    state: State
    evidence: list[Text] = []
    is_seeded: bool = False
    updated_at: AwareDatetime = Field(default_factory=now)


# Derived shapes (the Postgres views we will write later have the same meaning).


class StrategyStat(Record):
    student_id: UUID4
    gap_type: GapType
    method: Strategy
    uses: int
    independent_successes: int
    experiments: int
    last_used_at: AwareDatetime
    last_success_at: AwareDatetime | None


class SeenFingerprint(Record):
    student_id: UUID4
    fingerprint: Text
    kind: Literal["problem", "follow_up"]
