"""The handoff between the user module and the reasoning and tutor agent.

The real agent (with choose_strategy, the verifier and the regenerate loop behind it)
implements TutorPort; the user module never imports agent, verifier or gateway code.
Results arrive already checked, with the reply-check summary for the screen.
"""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from app.common.vocab import GapType, RejectionReason, ReplyOutcome, Strategy
from app.tutor.schema import (
    ChooseStrategyResult,
    FollowUpDraft,
    PriorDiagnosis,
    Step,
    TutorFollowUpOutput,
    TutorTeachingOutput,
)
from app.session.schema import Solution
from app.tutor.schema import ReplyCheckView
from app.verification.schema import StudentCheckResult


class ProblemSetup(BaseModel):
    """Produced once at session start: the concept the problem teaches, and the hidden solution."""

    concept_name: str
    solution: Solution


class TeachRequest(BaseModel):
    student_id: UUID  # the agent passes it to choose_strategy; history reaches it only that way
    problem: str
    concept_name: str
    solution: Solution
    student_text: str
    first_thought: bool
    hints_used: int
    teach_turns: int
    force_experiment: bool
    after_not_yet: bool
    prior: PriorDiagnosis | None = None  # the previous teaching turn, for code's repair check
    # The tutor's last delivered teaching move, which this text may be answering (None: work on the problem).
    tutor_message: str | None = None
    # Steps the student already got right earlier in this teaching cycle, so a reply may confirm them.
    earlier_correct_steps: list[Step] = []


class DraftOutcome(BaseModel):
    """What became of one teaching draft (kept in history for debugging; never shown to students)."""

    outcome: ReplyOutcome
    reason: RejectionReason | None = None
    note: str = ""
    method: Strategy | None = None


class TeachResult(BaseModel):
    output: TutorTeachingOutput
    # The method of a teaching move that reached the student. None for a probe, an acknowledgement, or a
    # fallback (a method whose reply was never sent is not shown or credited).
    method: ChooseStrategyResult | None
    reply_check: ReplyCheckView
    drafts: list[DraftOutcome] = []


class FollowUpRequest(BaseModel):
    student_id: UUID
    problem: str
    concept_name: str
    solution: Solution
    main_gap: GapType | None  # None when the student was right from the start (skip rule)
    hints_used: int
    retry_reason: str | None = None  # set when the last draft was a repeat
    # What the follow-up is built from (F14): the student's own work in this session.
    student_answers: list[str] = []  # their messages before the stress test, oldest first
    last_steps: list[Step] = []  # the last teaching turn's steps (where the gap showed)
    method: Strategy | None = None  # the method that was used while teaching, if any


class FollowUpResult(BaseModel):
    output: TutorFollowUpOutput
    message: str
    reply_check: ReplyCheckView


class JudgeRequest(BaseModel):
    problem: str
    solution: Solution
    follow_up: FollowUpDraft
    student_text: str
    hints_used: int


class TutorPort(Protocol):
    async def set_up(self, problem: str, subject: str | None) -> ProblemSetup: ...

    async def teach(self, request: TeachRequest) -> TeachResult: ...

    async def follow_up(self, request: FollowUpRequest) -> FollowUpResult: ...

    async def judge(self, request: JudgeRequest) -> StudentCheckResult: ...
