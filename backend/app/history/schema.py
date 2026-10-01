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
    model_validator,
)

from app.common.vocab import (
    Confidence,
    DecisionMode,
    Difficulty,
    Dimension,
    GapType,
    Perturbation,
    Phase,
    Rating,
    RejectionReason,
    SessionStatus,
    State,
    StepRole,
    StepStatus,
    Strategy,
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
    hidden_solution: SessionSolution | None = None
    started_at: AwareDatetime = Field(default_factory=now)
    ended_at: AwareDatetime | None = None


class Attempt(Record):
    id: UUID4 = Field(default_factory=uuid4)
    session_id: UUID4
    phase: Phase
    text: Text
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
        if self.concept_after == "verified" and self.result != "VERIFIED":
            raise ValueError("a concept becomes verified only on a VERIFIED result")
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
