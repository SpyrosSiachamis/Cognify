"""AgentTutor: the real TutorPort. One teaching turn is

    reason (LLM) -> rules (code) -> repair (code) -> choose_strategy (code)
      -> teach (LLM) -> verify (code, then LLM) -> approved reply, or back to teach (max 2), or a safe fallback

The diagnosis is made once per turn and never sees the method, so changing or
regenerating the teaching move cannot change it. set_up, follow_up and judge
are not built yet and use the stub, so the Maria story still runs end to end.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.history import HistoryStore
from app.session.schema import Solution
from app.user.ports import FollowUpRequest, FollowUpResult, JudgeRequest, ProblemSetup, TeachRequest, TeachResult
from app.user.stub_tutor import StubTutor
from app.verification.agent import check_reply
from app.verification.schema import ReplyCheckInput, ReplyCheckResult, StudentCheckResult

from .reasoning import diagnose
from .repair import gap_step, repaired
from .schema import (
    ChooseStrategyResult,
    ReasoningInput,
    ReplyCheckView,
    Step,
    TeachingInput,
    TutorDiagnosis,
    TutorTeachingOutput,
)
from .strategy import choose_strategy
from .language import ACKNOWLEDGE_REPLY, FALLBACK_REPLY, student_language, written_in
from .teaching import write_reply

MAX_REGENERATIONS = 2

Mode = Literal["teach", "probe", "acknowledge"]


class Draft(BaseModel):
    """One teaching try and what the checker said about it."""

    model_config = ConfigDict(extra="forbid")

    reply: str
    check: ReplyCheckResult | None = None
    failure: str | None = None


class TeachTrace(BaseModel):
    """What happened inside one turn. For scripts and tests; not part of the port."""

    model_config = ConfigDict(extra="forbid")

    diagnosis: TutorDiagnosis
    diagnosis_failure: str | None = None
    mode: Mode
    gap_step: Step | None = None
    strategy: ChooseStrategyResult | None = None
    gap_repaired: bool
    drafts: list[Draft] = []
    fallback: bool = False


def final_answers(solution: Solution) -> list[str]:
    """The strings the code leak check looks for: the result, and its number on its own."""
    answers = [solution.result]
    number = re.match(r"\s*(-?\d+(?:\.\d+)?)", solution.result)
    if number and number.group(1) != solution.result.strip():
        answers.append(number.group(1))
    return answers


def choose_mode(diagnosis: TutorDiagnosis, prior_gap: str | None, is_repaired: bool) -> Mode:
    """Deterministic: what kind of reply this turn needs."""
    if is_repaired:
        return "acknowledge"
    if diagnosis.evidence == "insufficient":
        return "teach" if prior_gap else "probe"
    if diagnosis.main_gap is None:
        return "acknowledge"
    return "teach"


class AgentTutor:
    def __init__(
        self,
        store: HistoryStore,
        model: Model | None = None,
        verifier_model: Model | None = None,
        timeout: float = gateway.DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._store = store
        self._model = model or gateway.model_for("TUTOR_MODEL_ID")
        self._verifier_model = verifier_model or self._model
        self._timeout = timeout
        self._stub = StubTutor()
        self.last_trace: TeachTrace | None = None

    # ---- not built yet: the stub keeps the session flow working ----

    async def set_up(self, problem: str, subject: str | None) -> ProblemSetup:
        return await self._stub.set_up(problem, subject)

    async def follow_up(self, request: FollowUpRequest) -> FollowUpResult:
        return await self._stub.follow_up(request)

    async def judge(self, request: JudgeRequest) -> StudentCheckResult:
        return await self._stub.judge(request)

    # ---- one teaching turn ----

    async def teach(self, request: TeachRequest) -> TeachResult:
        reasoned = await diagnose(
            ReasoningInput(problem=request.problem, attempt=request.student_text, final_answer=request.solution.result),
            self._model,
            self._timeout,
        )
        diagnosis = reasoned.value
        prior = request.prior
        prior_gap = prior.main_gap if prior else None
        is_repaired = repaired(prior, diagnosis.steps)
        mode = choose_mode(diagnosis, prior_gap, is_repaired)

        # No new evidence, but a gap is still being taught: keep teaching that gap.
        if mode == "teach" and diagnosis.main_gap is None:
            diagnosis = diagnosis.model_copy(update={"main_gap": prior_gap})
        step = gap_step(
            prior.steps if diagnosis.evidence == "insufficient" and prior else diagnosis.steps, diagnosis.main_gap
        )
        strategy = (
            choose_strategy(self._store, request.student_id, diagnosis.main_gap, request.force_experiment)
            if mode == "teach" and diagnosis.main_gap is not None
            else None
        )
        trace = TeachTrace(
            diagnosis=diagnosis,
            diagnosis_failure=None if reasoned.ok else f"{reasoned.failure}: {reasoned.detail}",
            mode=mode,
            gap_step=step,
            strategy=strategy,
            gap_repaired=is_repaired,
        )
        self.last_trace = trace

        if mode == "acknowledge":
            reply = ACKNOWLEDGE_REPLY[student_language(request.student_text)]
            view = ReplyCheckView(approved=True, summary="No teaching move needed; fixed acknowledgement.")
        else:
            reply, view = await self._teach_and_verify(request, diagnosis, mode, step, strategy, trace)

        output = TutorTeachingOutput(**diagnosis.model_dump(), gap_repaired=is_repaired, reply=reply)
        return TeachResult(output=output, method=strategy, reply_check=view)

    async def _teach_and_verify(
        self,
        request: TeachRequest,
        diagnosis: TutorDiagnosis,
        mode: Mode,
        step: Step | None,
        strategy: ChooseStrategyResult | None,
        trace: TeachTrace,
    ) -> tuple[str, ReplyCheckView]:
        teaching_input = TeachingInput(
            problem=request.problem,
            attempt=request.student_text,
            mode=mode,
            diagnosis=diagnosis,
            gap_step=step,
            strategy=strategy,
            hints_used=request.hints_used,
            solution_steps=request.solution.steps,
            language=student_language(request.student_text),
        )
        for _ in range(1 + MAX_REGENERATIONS):
            written = await write_reply(teaching_input, self._model, self._timeout)
            if not written.ok:
                trace.drafts.append(Draft(reply="", failure=f"teaching: {written.failure}: {written.detail}"))
                break
            reply = written.value.reply
            if not written_in(reply, teaching_input.language):
                # Code check: the wrong language never reaches the verifier or the student.
                trace.drafts.append(Draft(reply=reply, failure=f"language: not written in {teaching_input.language}"))
                teaching_input = teaching_input.model_copy(update={
                    "retry_reason": None,
                    "retry_note": f"Your reply was not in {teaching_input.language}. Write it entirely in "
                    f"{teaching_input.language}, the student's language.",
                })
                continue
            checked = await check_reply(
                ReplyCheckInput(
                    problem=request.problem,
                    attempt=request.student_text,
                    reply=reply,
                    method=strategy.method if strategy else None,
                    hints_used=request.hints_used,
                    hidden_solution=" ".join(request.solution.steps),
                ),
                self._verifier_model,
                final_answers(request.solution),
                self._timeout,
            )
            if not checked.ok:
                # Never send an unchecked reply.
                trace.drafts.append(Draft(reply=reply, failure=f"verifier: {checked.failure}: {checked.detail}"))
                break
            check = checked.value
            trace.drafts.append(Draft(reply=reply, check=check))
            if check.approved:
                return reply, ReplyCheckView(approved=True, summary=check.note)
            teaching_input = teaching_input.model_copy(update={"retry_reason": check.reason, "retry_note": check.note})
        trace.fallback = True
        return FALLBACK_REPLY[teaching_input.language], ReplyCheckView(approved=False, summary="Safe fallback used.")
