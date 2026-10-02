"""Learner shapes (docs/API_CONTRACT.md, Part A): the two learner views and the error shape; and the
development session-trace views (only served when DEBUG_TRACE is on)."""

from typing import Annotated

from pydantic import UUID4, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.common.contract import CONCEPT, MARIA, contract
from app.common.vocab import GapType, Phase, SessionStatus, State, Strategy
from app.history.schema import TraceEvent

Text = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


# ---- development session trace (DEBUG_TRACE only; never on a public deployment: it holds hidden solutions) ----


class TraceSummary(StrictModel):
    session_id: UUID4
    student_id: UUID4
    problem: str
    status: SessionStatus
    phase: Phase
    started_at: AwareDatetime
    ended_at: AwareDatetime | None
    events: int


class TraceIndex(StrictModel):
    sessions: list[TraceSummary]


class SessionTraceView(StrictModel):
    session_id: UUID4
    events: list[TraceEvent]


class TraceExport(StrictModel):
    exported_at: AwareDatetime
    sessions: list[SessionTraceView]
