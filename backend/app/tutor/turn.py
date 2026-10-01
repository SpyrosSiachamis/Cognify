"""One Master teaching turn, and a session that loops turns.

Flow per turn:
    student text -> tutor (diagnose + draft reply) -> reply check (code, then verifier)
      approved -> reply goes to the student
      rejected -> tutor regenerates with the reason (max 2), then a safe fallback

The models are passed in, so the provider stays in ai_gateway (rule 4).
"""

import asyncio

from pydantic import BaseModel, ConfigDict
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models import Model

from app.verification.agent import check_reply
from app.verification.schema import ReplyCheckInput, ReplyCheckResult

from .agent import run_tutor
from .schema import TranscriptLine, TutorInput, TutorTeachingOutput

MAX_REGENERATIONS = 2
MAX_TEACH_TURNS = 4
CALL_TIMEOUT_SECONDS = 45.0
# Invalid output after the retry, a provider error, or a timeout: all end in the fallback.
MODEL_FAILURES = (UnexpectedModelBehavior, ModelAPIError, TimeoutError)
FALLBACK_REPLY = "Let's slow down for a moment. Which step of your answer are you least sure about, and why?"


class Draft(BaseModel):
    """One tutor try and what the checker said about it."""

    model_config = ConfigDict(extra="forbid")

    output: TutorTeachingOutput | None
    check: ReplyCheckResult | None
    error: str | None = None


class TurnResult(BaseModel):
    """What one turn produced. reply is what the student sees."""

    model_config = ConfigDict(extra="forbid")

    drafts: list[Draft]
    reply: str
    approved: TutorTeachingOutput | None
    fallback: bool


async def run_turn(
    tutor_input: TutorInput,
    tutor_model: Model,
    verifier_model: Model,
    final_answers: list[str] = [],
    timeout: float = CALL_TIMEOUT_SECONDS,
) -> TurnResult:
    drafts: list[Draft] = []
    current = tutor_input
    for _ in range(1 + MAX_REGENERATIONS):
        try:
            output = await asyncio.wait_for(run_tutor(current, tutor_model), timeout)
        except MODEL_FAILURES as exc:
            drafts.append(Draft(output=None, check=None, error=f"tutor: {type(exc).__name__}: {exc}"))
            break
        check_input = ReplyCheckInput(
            problem=current.problem,
            attempt=current.attempt,
            reply=output.reply,
            method=current.strategy.method if current.strategy else None,
            hints_used=current.hints_used,
            hidden_solution=current.hidden_solution,
        )
        try:
            check = await asyncio.wait_for(check_reply(check_input, verifier_model, final_answers), timeout)
        except MODEL_FAILURES as exc:
            # Never send an unchecked reply.
            drafts.append(Draft(output=output, check=None, error=f"verifier: {type(exc).__name__}: {exc}"))
            break
        drafts.append(Draft(output=output, check=check))
        if check.approved:
            return TurnResult(drafts=drafts, reply=output.reply, approved=output, fallback=False)
        current = current.model_copy(update={"retry_reason": check.reason, "retry_note": check.note})
    return TurnResult(drafts=drafts, reply=FALLBACK_REPLY, approved=None, fallback=True)


class TutorSession:
    """Keeps the transcript and hint count between turns. In memory only; storage is history's job."""

    def __init__(self, base: TutorInput, tutor_model: Model, verifier_model: Model, final_answers: list[str] = []):
        self.base = base
        self.tutor_model = tutor_model
        self.verifier_model = verifier_model
        self.final_answers = final_answers
        self.transcript: list[TranscriptLine] = list(base.transcript)
        self.hints_used = base.hints_used
        self.teach_turns = 0
        self.ready_for_stress_test = False
        self.target_gap = base.target_gap
        self.timeout = CALL_TIMEOUT_SECONDS

    async def send(self, text: str) -> TurnResult:
        phase = "ask_first_thought" if not self.transcript else "teach"
        turn_input = self.base.model_copy(
            update={
                "attempt": text,
                "phase": phase,
                "hints_used": self.hints_used,
                "transcript": list(self.transcript),
                "retry_reason": None,
                "retry_note": None,
                "target_gap": self.target_gap,
            }
        )
        result = await run_turn(turn_input, self.tutor_model, self.verifier_model, self.final_answers, self.timeout)
        self.transcript += [
            TranscriptLine(speaker="student", text=text),
            TranscriptLine(speaker="tutor", text=result.reply),
        ]
        if self.target_gap is None and result.approved is not None:
            self.target_gap = result.approved.main_gap
        self.teach_turns += 1
        self.hints_used += 1
        approved = result.approved
        repaired = approved is not None and approved.gap_repaired
        all_correct = approved is not None and all(step.status == "correct" for step in approved.steps)
        # Move-on and skip rules (docs/ARCHITECTURE.md): gap repaired, every step already
        # correct, or after 4 teach turns.
        self.ready_for_stress_test = repaired or all_correct or self.teach_turns >= MAX_TEACH_TURNS
        return result
