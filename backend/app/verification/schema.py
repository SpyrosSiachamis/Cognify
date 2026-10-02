"""Verifier result (docs/API_CONTRACT.md, Part B): one shape per mode.

The student check does not carry VERIFIED: code decides that.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.common.vocab import GapType, Rating, RejectionReason, Strategy

Text = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Verdict(StrictModel):
    approved: bool
    reason: RejectionReason | None = None
    note: Text

    @model_validator(mode="after")
    def reason_matches_approval(self) -> "_Verdict":
        if self.approved and self.reason is not None:
            raise ValueError("an approved result must not have a rejection reason")
        if not self.approved and self.reason is None:
            raise ValueError("a rejected result needs a rejection reason")
        return self


class ReplyCheckInput(StrictModel):
    """Built by code for one reply check; sent to the verifier as JSON."""

    problem: Text
    attempt: Text
    reply: Text
    method: Strategy | None = None
    hints_used: int = Field(default=0, ge=0)
    hidden_solution: str | None = None
    # What the reply is meant to target and how (filled by the tutor; all optional).
    main_gap: GapType | None = None
    gap_step: str | None = None  # the step role, with the student's own words if any
    error_mismatch: str | None = None  # what the student's result really is versus what is needed
    method_definition: str | None = None  # what the chosen method requires of a reply
    language: str | None = None
    # The student's own derived results (quotes), which a reply may repeat or confirm: not a leak.
    student_demonstrated: list[str] = []


class FollowUpCheckInput(StrictModel):
    """Built by code for one follow-up check; sent to the verifier as JSON."""

    original_problem: Text
    follow_up: Text
    concept_invariant: Text
    target_gap: GapType
    target_step: str
    perturbation: str
    hidden_rubric: list[Text]


class StudentCheckInput(StrictModel):
    """Built by code for judging the student's answer to the stress test."""

    follow_up: Text
    concept_invariant: Text
    hidden_rubric: list[Text]
    student_text: Text
    # The step that was the student's gap: own work must show it (a guessed right answer does not).
    target_gap: GapType | None = None
    target_step: str | None = None


class ReplyCheckResult(_Verdict):
    """Produced by the verifier for a tutor reply; read by code (regenerate or send)."""

    mode: Literal["reply_check"]


class FollowUpCheckResult(_Verdict):
    """Produced by the verifier for a follow-up problem; read by code."""

    mode: Literal["follow_up_check"]


class StudentCheckResult(StrictModel):
    """Produced by the verifier for the student's follow-up attempt; read by code, which decides VERIFIED."""

    mode: Literal["student_check"]
    correct: bool
    reasoning_quality: Rating
    own_work: bool
    note: Text


VerifierResult = Annotated[
    ReplyCheckResult | FollowUpCheckResult | StudentCheckResult,
    Field(discriminator="mode"),
]

# Validate a raw dict into the right result: VerifierResultAdapter.validate_python(data)
VerifierResultAdapter: TypeAdapter[VerifierResult] = TypeAdapter(VerifierResult)
