"""Tutor shapes (docs/API_CONTRACT.md, Part B): choose_strategy, the reasoning and teaching steps, and their output."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.contract import PROBLEM, SESSION, contract
from app.common.vocab import (
    Confidence,
    DecisionMode,
    Difficulty,
    Dimension,
    Evidence,
    GapType,
    Perturbation,
    Phase,
    Rating,
    RejectionReason,
    StepRole,
    StepStatus,
    Strategy,
)

Text = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- choose_strategy tool (code, not AI) ----


class ChooseStrategyInput(StrictModel):
    """What the tutor agent passes to the tool. Read by strategy_choice."""

    student_id: UUID
    gap_type: GapType
    concept: Text


class EvidenceCounts(StrictModel):
    uses: int = Field(ge=0)
    independent_successes: int = Field(ge=0)

    @model_validator(mode="after")
    def successes_within_uses(self) -> "EvidenceCounts":
        if self.independent_successes > self.uses:
            raise ValueError("independent_successes cannot be more than uses")
        return self


class ChooseStrategyResult(StrictModel):
    """Produced by strategy_choice, read by the tutor agent; the app records it."""

    method: Strategy
    mode: DecisionMode
    reason: Text
    evidence: EvidenceCounts
    last_success_days_ago: int | None = Field(default=None, ge=0)


# ---- tutor agent output ----


class Step(StrictModel):
    """One step of the student's answer, with their own words as evidence."""

    role: StepRole
    status: StepStatus
    quote: str | None = None

    @field_validator("quote", mode="before")
    @classmethod
    def empty_quote_is_none(cls, value: object) -> object:
        # Models often send "" or [] for "no quote".
        return None if value in ("", []) else value

    @model_validator(mode="after")
    def quote_unless_missing(self) -> "Step":
        if self.status != "missing" and not self.quote:
            raise ValueError("a correct or wrong step must quote the student's words")
        return self


class Alternative(StrictModel):
    gap: GapType
    confidence: Confidence


class DimensionRating(StrictModel):
    name: Dimension
    state: Rating
    evidence: Text


class TutorDiagnosis(StrictModel):
    """Produced by the reasoning step from the student's work alone (no method, no history).

    main_gap is None when no gap is demonstrated: either every step holds, or the
    evidence is insufficient to tell (then code asks a probe instead of teaching).
    """

    steps: list[Step] = Field(min_length=1)
    dimensions: list[DimensionRating] = []
    main_gap: GapType | None = None
    alternatives: list[Alternative] = []
    confidence: Confidence
    evidence: Evidence = "sufficient"

    @model_validator(mode="after")
    def diagnosis_is_consistent(self) -> "TutorDiagnosis":
        if any(alt.gap == self.main_gap for alt in self.alternatives):
            raise ValueError("the main gap must not also appear in alternatives")
        if self.evidence == "insufficient" and self.confidence != "low":
            raise ValueError("insufficient evidence means low confidence")
        if self.evidence == "sufficient" and not any(step.quote for step in self.steps):
            raise ValueError("a diagnosis needs at least one quoted piece of student evidence")
        if self.main_gap is None and self.evidence == "sufficient" and any(s.status == "wrong" for s in self.steps):
            raise ValueError("a wrong step needs a main gap")
        return self


class TutorTeachingOutput(TutorDiagnosis):
    """One teaching turn: the diagnosis, plus code's repair check and the approved reply."""

    gap_repaired: bool
    reply: Text


class PriorDiagnosis(StrictModel):
    """The previous teaching turn of this session, for the repair check. Built by the session flow."""

    steps: list[Step] = Field(min_length=1)
    main_gap: GapType | None = None


# ---- what the two LLM steps receive (sent as JSON) ----

TeachingMode = Literal["teach", "probe"]


class ReasoningInput(StrictModel):
    """The reasoning step sees the student's work only: no method, no history, no solution route."""

    problem: Text
    attempt: Text
    final_answer: str | None = None


class TeachingInput(StrictModel):
    """The teaching step gets the finished diagnosis and code's choice of mode and method."""

    problem: Text
    attempt: Text
    mode: TeachingMode
    diagnosis: TutorDiagnosis
    gap_step: Step | None = None
    strategy: ChooseStrategyResult | None = None
    method_definition: str | None = None  # what strategy.method requires; the verifier checks the same text
    hints_used: int = Field(default=0, ge=0)
    solution_steps: list[Text] = []
    language: Literal["English", "Greek"] = "English"
    retry_reason: RejectionReason | None = None
    retry_note: str | None = None


class TeachingReply(StrictModel):
    reply: Text


class FollowUpDraft(StrictModel):
    problem: Text
    concept_invariant: Text
    target_gap: GapType
    target_step: StepRole
    perturbation: Perturbation
    difficulty: Difficulty
    hidden_rubric: list[Text]

    @model_validator(mode="after")
    def rubric_not_empty(self) -> "FollowUpDraft":
        if not self.hidden_rubric:
            raise ValueError("hidden_rubric needs at least one item")
        return self


class TutorFollowUpOutput(StrictModel):
    """Produced by the tutor agent for the stress test. The hidden rubric never leaves the backend."""

    follow_up: FollowUpDraft


class Level1Answer(StrictModel):
    """Produced by the single Level 1 call; read by the answer route. Stateless."""

    result: Text
    steps: list[Text] = Field(min_length=1)


# ---- POST /api/answer (Level 1) ----


class AnswerRequest(StrictModel):
    """Sent by the frontend; read by the answer route."""

    model_config = contract({"problem": PROBLEM, "subject": "physics"})

    problem: str = Field(min_length=1, max_length=2000)
    subject: str | None = None


class AnswerResponse(StrictModel):
    """Level 1 result. Writes nothing and never counts as evidence."""

    model_config = contract(
        {
            "result": "20.4 m",
            "steps": ["At the highest point the velocity is 0 m/s.", "h = 400 / 19.6 = 20.4 m."],
            "counts_as_evidence": False,
        }
    )

    result: Text
    steps: list[Text] = Field(min_length=1)
    counts_as_evidence: bool = False

    @model_validator(mode="after")
    def never_evidence(self) -> "AnswerResponse":
        if self.counts_as_evidence:
            raise ValueError("a Level 1 answer never counts as evidence")
        return self


# ---- tutor turn (POST /api/session/{id}/attempt) ----


class DiagnosisView(StrictModel):
    steps: list[Step] = Field(min_length=1)
    main_gap: GapType | None = None
    alternatives: list[Alternative] = []
    confidence: Confidence

    @model_validator(mode="after")
    def main_gap_not_in_alternatives(self) -> "DiagnosisView":
        if any(alt.gap == self.main_gap for alt in self.alternatives):
            raise ValueError("the main gap must not also appear in alternatives")
        return self


class MethodView(StrictModel):
    name: Strategy
    mode: DecisionMode
    experiment: bool
    reason: Text

    @model_validator(mode="after")
    def experiment_matches_mode(self) -> "MethodView":
        if self.experiment != (self.mode == "experiment"):
            raise ValueError("experiment must be true exactly when mode is experiment")
        return self


class FollowUpView(StrictModel):
    """Only the problem text, never the rubric."""

    problem: Text


class ReplyCheckView(StrictModel):
    approved: bool
    summary: Text


class TutorTurn(StrictModel):
    """A teaching turn or the stress-test follow-up. Built by code from the approved reply."""

    model_config = contract(
        {
            "session_id": SESSION,
            "phase": "teach",
            "message": "Let's draw it. Sketch the ball going up and mark where its speed becomes 0.",
            "diagnosis": {
                "steps": [
                    {"role": "choose_method", "status": "wrong", "quote": "I do not know how to get the height"}
                ],
                "main_gap": "recognition",
                "alternatives": [{"gap": "representation", "confidence": "low"}],
                "confidence": "medium",
            },
            "method": {
                "name": "visual_decomposition",
                "mode": "best_known",
                "experiment": False,
                "reason": "Worked 7 of 9 times for you on recognition gaps.",
            },
            "hints_used": 0,
            "reply_check": {"approved": True, "summary": "No answer given. Method matches: visual_decomposition."},
        },
        {
            "session_id": SESSION,
            "phase": "stress_test",
            "message": "Now I am removing the support. New problem, same underlying idea, different surface.",
            "follow_up": {"problem": "A stone is launched upward at 15 m/s from a balcony."},
            "hints_used": 1,
            "reply_check": {"approved": True, "summary": "Follow-up keeps the principle."},
        },
    )

    session_id: UUID4
    phase: Phase
    message: Text
    diagnosis: DiagnosisView | None = None
    method: MethodView | None = None
    follow_up: FollowUpView | None = None
    hints_used: int = Field(ge=0)
    reply_check: ReplyCheckView

    @model_validator(mode="after")
    def phase_matches_content(self) -> "TutorTurn":
        if self.phase in ("verdict", "exited"):
            raise ValueError("a tutor turn is a teaching turn or a stress test, not a verdict or exit")
        if (self.phase == "stress_test") != (self.follow_up is not None):
            raise ValueError("a follow-up appears in the stress_test phase and only there")
        return self
