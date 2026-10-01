"""Tutor shapes (docs/API_CONTRACT.md, Part B): the choose_strategy tool and the agent's output."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.vocab import (
    Confidence,
    DecisionMode,
    Difficulty,
    Dimension,
    GapType,
    Perturbation,
    Rating,
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


class TutorTeachingOutput(StrictModel):
    """Produced by the tutor agent for a teaching turn; read by verification, then by code."""

    steps: list[Step] = Field(min_length=1)
    dimensions: list[DimensionRating] = []
    main_gap: GapType
    alternatives: list[Alternative] = []
    confidence: Confidence
    gap_repaired: bool
    reply: Text

    @model_validator(mode="after")
    def diagnosis_is_consistent(self) -> "TutorTeachingOutput":
        if any(alt.gap == self.main_gap for alt in self.alternatives):
            raise ValueError("the main gap must not also appear in alternatives")
        if not any(step.quote for step in self.steps):
            raise ValueError("a diagnosis needs at least one quoted piece of student evidence")
        return self


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
