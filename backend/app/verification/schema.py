"""Verifier result (docs/API_CONTRACT.md, Part B): one shape per mode.

The student check does not carry VERIFIED: code decides that.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.common.vocab import Rating, RejectionReason, Strategy

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
