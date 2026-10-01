"""Frontend <-> backend shapes (docs/API_CONTRACT.md, Part A), one request and response per endpoint.

The hidden solution, hidden rubric and verifier notes have no field in any
response model, so they cannot leave the backend. The only solution field is the
one returned by an explicit exit.
"""

from typing import Annotated, Any

from pydantic import UUID4, BaseModel, ConfigDict, Field, model_validator

from app.common.vocab import (
    Confidence,
    DecisionMode,
    GapType,
    Phase,
    State,
    Strategy,
    VerdictResult,
)
from app.tutor.schema import Alternative, EvidenceCounts, Step

Text = Annotated[str, Field(min_length=1)]

MARIA = "16e82ef2-adee-4671-8393-c6b50ac91672"
SESSION = "d96e9546-b0bf-43a7-acdc-42f43ae8adac"
CONCEPT = "44d54897-9ec4-45b9-8da1-d4ea95697d1d"
PROBLEM = (
    "A ball is thrown vertically upward with an initial velocity of 20 m/s. "
    "How high does it go before it starts to fall? (Use g = 9.8 m/s^2)"
)


def contract(*examples: dict[str, Any]) -> ConfigDict:
    """Strict config; the examples show up in the OpenAPI schema."""
    return ConfigDict(extra="forbid", json_schema_extra={"examples": list(examples)})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


# ---- POST /api/session (start Master) ----


class SessionStartRequest(StrictModel):
    model_config = contract(
        {"problem": PROBLEM, "subject": "physics", "student_id": MARIA, "force_experiment": False}
    )

    problem: str = Field(min_length=1, max_length=2000)
    subject: str | None = None
    student_id: UUID4
    force_experiment: bool = False


class SessionStartResponse(StrictModel):
    model_config = contract(
        {
            "session_id": SESSION,
            "phase": "ask_first_thought",
            "message": "Before I help, what would you try first? Even an incomplete idea is useful.",
            "hints_used": 0,
        }
    )

    session_id: UUID4
    phase: Phase
    message: Text
    hints_used: int = Field(ge=0)


# ---- POST /api/session/{id}/attempt ----


class StudentAttempt(StrictModel):
    """The same shape on every turn."""

    model_config = contract({"text": "I found the time to the top, but not the height."})

    text: Text


class DiagnosisView(StrictModel):
    steps: list[Step] = Field(min_length=1)
    main_gap: GapType
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


class ConceptChange(StrictModel):
    concept_id: UUID4
    name: Text
    before: State
    after: State


class StrategyChange(StrictModel):
    gap: GapType
    method: Strategy
    before: EvidenceCounts
    after: EvidenceCounts


class VerdictChanges(StrictModel):
    concept: ConceptChange
    strategy: StrategyChange


class Verdict(StrictModel):
    result: VerdictResult
    evidence: Text
    independent: bool
    remaining_gap: GapType | None = None
    changes: VerdictChanges

    @model_validator(mode="after")
    def verified_needs_independence(self) -> "Verdict":
        if self.result == "VERIFIED" and not self.independent:
            raise ValueError("VERIFIED requires independent=True (a lucky answer is NOT YET)")
        return self


class VerdictTurn(StrictModel):
    """The end of the stress test. VERIFIED is decided by code, not by the model."""

    model_config = contract(
        {
            "session_id": SESSION,
            "phase": "verdict",
            "session_over": True,
            "verdict": {
                "result": "VERIFIED",
                "evidence": "Chose the equation that needs no time, with no hints on this problem.",
                "independent": True,
                "remaining_gap": None,
                "changes": {
                    "concept": {"concept_id": CONCEPT, "name": "Constant-acceleration kinematics", "before": "fragile", "after": "verified"},
                    "strategy": {
                        "gap": "recognition",
                        "method": "visual_decomposition",
                        "before": {"uses": 9, "independent_successes": 7},
                        "after": {"uses": 10, "independent_successes": 8},
                    },
                },
            },
        }
    )

    session_id: UUID4
    phase: Phase
    session_over: bool
    message: str | None = None
    verdict: Verdict

    @model_validator(mode="after")
    def verdict_phase_and_ending(self) -> "VerdictTurn":
        if self.phase != "verdict":
            raise ValueError("a verdict turn has phase verdict")
        if self.verdict.result == "VERIFIED" and not self.session_over:
            raise ValueError("a VERIFIED verdict ends the session")
        return self


# What POST /api/session/{id}/attempt returns.
AttemptResponse = TutorTurn | VerdictTurn


# ---- POST /api/session/{id}/exit ----


class Solution(StrictModel):
    result: Text
    steps: list[Text] = Field(min_length=1)


class ExitResponse(StrictModel):
    """Explicit exit: the solution is returned and no evidence is recorded."""

    model_config = contract(
        {
            "phase": "exited",
            "solution": {"result": "20.4 m", "steps": ["At the highest point v = 0.", "h = 400 / 19.6 = 20.4 m."]},
            "evidence_recorded": False,
        }
    )

    phase: Phase
    solution: Solution
    evidence_recorded: bool = False

    @model_validator(mode="after")
    def exited_without_evidence(self) -> "ExitResponse":
        if self.phase != "exited":
            raise ValueError("an exit response has phase exited")
        if self.evidence_recorded:
            raise ValueError("exit records no evidence")
        return self


# ---- GET /api/learner/{student_id} and GET /api/strategies/{student_id} ----


class LearnerConcept(StrictModel):
    concept_id: UUID4
    name: Text
    state: State
    evidence: list[Text] = []


class LearnerView(StrictModel):
    model_config = contract(
        {
            "student_id": MARIA,
            "display_name": "Maria",
            "is_seeded": True,
            "concepts": [
                {
                    "concept_id": CONCEPT,
                    "name": "Constant-acceleration kinematics",
                    "state": "fragile",
                    "evidence": ["Seeded demo history: recognition gap in 3 earlier sessions."],
                }
            ],
        }
    )

    student_id: UUID4
    display_name: Text
    is_seeded: bool
    concepts: list[LearnerConcept]


class StrategyRow(StrictModel):
    gap: GapType
    method: Strategy
    uses: int = Field(ge=0)
    independent_successes: int = Field(ge=0)
    experiments: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_make_sense(self) -> "StrategyRow":
        if self.independent_successes > self.uses or self.experiments > self.uses:
            raise ValueError("successes and experiments cannot be more than uses")
        return self


class MethodTotal(StrictModel):
    """One method summed across gap types."""

    method: Strategy
    uses: int = Field(ge=0)
    independent_successes: int = Field(ge=0)

    @model_validator(mode="after")
    def successes_within_uses(self) -> "MethodTotal":
        if self.independent_successes > self.uses:
            raise ValueError("independent_successes cannot be more than uses")
        return self


class StrategyView(StrictModel):
    model_config = contract(
        {
            "student_id": MARIA,
            "display_name": "Maria",
            "is_seeded": True,
            "rows": [
                {"gap": "recognition", "method": "visual_decomposition", "uses": 9, "independent_successes": 7, "experiments": 0}
            ],
            "methods": [{"method": "visual_decomposition", "uses": 9, "independent_successes": 7}],
        }
    )

    student_id: UUID4
    display_name: Text
    is_seeded: bool
    rows: list[StrategyRow]
    methods: list[MethodTotal]


# ---- error shape (all endpoints) ----


class ErrorBody(StrictModel):
    code: Text
    message: Text
    retryable: bool


class ErrorResponse(StrictModel):
    model_config = contract(
        {"error": {"code": "model_unavailable", "message": "Please try again.", "retryable": True}}
    )

    error: ErrorBody
