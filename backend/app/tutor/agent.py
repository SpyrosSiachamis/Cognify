"""AgentTutor: the real TutorPort. One teaching turn is

    reason (LLM) -> rules (code) -> repair (code) -> choose_strategy (code)
      -> teach (LLM) -> verify (code, then LLM) -> approved reply, or back to teach (max 2), or a safe fallback

The diagnosis is made once per turn and never sees the method, so changing or
regenerating the teaching move cannot change it.

set_up names the concept and writes the hidden solution; follow_up writes the
personal stress test (F14/F15); judge gives evidence on the student's answer, and
the session flow (code) decides VERIFIED (F16). None of these fall back to a fake
answer: a failure raises, and the session turns it into a retryable error.
"""

import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.history import HistoryStore
from app.session.schema import Solution
from app.session.schema import Solution as SessionSolution
from app.user.ports import FollowUpRequest, FollowUpResult, JudgeRequest, ProblemSetup, TeachRequest, TeachResult
from app.verification.agent import check_reply, check_student
from app.verification.schema import ReplyCheckInput, ReplyCheckResult, StudentCheckInput, StudentCheckResult

from .evidence import substantive
from .follow_up import FollowUpInput, write_follow_up
from .setup import solve

from .reasoning import diagnose
from .repair import assess_repair, gap_step
from .schema import (
    ChooseStrategyResult,
    TutorFollowUpOutput,
    ReasoningInput,
    ReplyCheckView,
    Step,
    TeachingInput,
    TutorDiagnosis,
    TutorTeachingOutput,
)
from .strategy import choose_strategy
from .language import ACKNOWLEDGE_REPLY, FALLBACK_REPLY, STRESS_TEST_MESSAGE, student_language, written_in
from .methods import GUIDANCE, METHOD_DEFINITIONS
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
    repair_reason: str = ""
    drafts: list[Draft] = []
    fallback: bool = False


def final_answers(solution: Solution) -> list[str]:
    """The strings the code leak check looks for: the result, and its number on its own."""
    answers = [solution.result]
    number = re.match(r"\s*(-?\d+(?:\.\d+)?)", solution.result)
    if number and number.group(1) != solution.result.strip():
        answers.append(number.group(1))
    return answers


def _describe(step: Step | None) -> str | None:
    """The gap step as the verifier reads it: the role, and the student's words if any."""
    if step is None:
        return None
    words = f': "{step.quote}"' if step.quote else " (the student did not write this step)"
    return f"{step.role} ({step.status}){words}"


def carry_gap(diagnosis: TutorDiagnosis, gap: str | None) -> TutorDiagnosis:
    """The diagnosis with the gap still being taught as its main gap, validated."""
    data = diagnosis.model_dump()
    data["main_gap"] = gap
    data["alternatives"] = [a for a in data["alternatives"] if a["gap"] != gap]
    return TutorDiagnosis.model_validate(data)


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
        on_trace: Callable[[TeachTrace], None] | None = None,
    ) -> None:
        self._store = store
        self._model = model or gateway.model_for("TUTOR_MODEL_ID")
        self._verifier_model = verifier_model or self._model
        self._timeout = timeout
        # One AgentTutor serves every session, so nothing per-turn is stored on it.
        # A trace goes back with the call (teach_with_trace) or to a caller-owned sink.
        self._on_trace = on_trace

    # ---- session start: concept and hidden solution ----

    async def set_up(self, problem: str, subject: str | None) -> ProblemSetup:
        solved = await solve(problem, subject, self._store, self._model, self._timeout)
        if not solved.ok:
            raise RuntimeError(f"set_up failed: {solved.failure}: {solved.detail}") # type: ignore
        out = solved.value
        return ProblemSetup(concept_name=out.concept_name, solution=SessionSolution(result=out.result, steps=out.steps))

    # ---- F14 + F15: the personal stress test ----

    async def follow_up(self, request: FollowUpRequest) -> FollowUpResult:
        language = student_language(request.student_answers[-1]) if request.student_answers else "English"
        draft, check, _ = await write_follow_up(
            FollowUpInput(
                problem=request.problem,
                concept_name=request.concept_name,
                solution_steps=request.solution.steps,
                main_gap=request.main_gap,
                gap_step=gap_step(request.last_steps, request.main_gap) if request.last_steps else None,
                student_answers=request.student_answers,
                method=request.method,
                language=language,
                retry_note=request.retry_reason,  # set by the session when the last one repeated a seen problem
            ),
            self._model, self._verifier_model, self._timeout,
        )
        return FollowUpResult(
            output=TutorFollowUpOutput(follow_up=draft),
            message=STRESS_TEST_MESSAGE[language],
            reply_check=ReplyCheckView(approved=True, summary=check.note),
        )

    # ---- F16: evidence on the stress-test answer (code decides VERIFIED) ----

    async def judge(self, request: JudgeRequest) -> StudentCheckResult:
        checked = await check_student(
            StudentCheckInput(
                follow_up=request.follow_up.problem,
                concept_invariant=request.follow_up.concept_invariant,
                hidden_rubric=request.follow_up.hidden_rubric,
                student_text=request.student_text,
                target_gap=request.follow_up.target_gap,
                target_step=request.follow_up.target_step,
            ),
            self._verifier_model, self._timeout,
        )
        if not checked.ok:
            raise RuntimeError(f"judge failed: {checked.failure}: {checked.detail}") # type: ignore
        result = checked.value
        # Deterministic: an answer with no reasoning in it is not evidence of independent work.
        if result.own_work and not substantive(request.student_text):
            result = StudentCheckResult.model_validate(
                {**result.model_dump(), "own_work": False,
                 "note": f"{result.note} (No reasoning shown, so it does not count as independent work.)"}
            )
        return result

    # ---- one teaching turn ----

    async def teach(self, request: TeachRequest) -> TeachResult:
        result, trace = await self.teach_with_trace(request)
        if self._on_trace is not None:
            self._on_trace(trace)
        return result

    async def teach_with_trace(self, request: TeachRequest) -> tuple[TeachResult, TeachTrace]:
        """One teaching turn, and what happened inside it. Nothing is kept between calls."""
        reasoned = await diagnose(
            ReasoningInput(problem=request.problem, attempt=request.student_text, final_answer=request.solution.result),
            self._model,
            self._timeout,
        )
        diagnosis = reasoned.value
        prior = request.prior
        prior_gap = prior.main_gap if prior else None
        repair = assess_repair(prior, diagnosis)
        is_repaired = repair.repaired
        mode = choose_mode(diagnosis, prior_gap, is_repaired)

        # No new evidence, but a gap is still being taught: keep teaching that gap. Built as a
        # new, validated diagnosis (the carried gap cannot also stay an alternative).
        if mode == "teach" and diagnosis.main_gap is None:
            diagnosis = carry_gap(diagnosis, prior_gap)
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
            diagnosis_failure=None if reasoned.ok else f"{reasoned.failure}: {reasoned.detail}", # type: ignore
            mode=mode,
            gap_step=step,
            strategy=strategy,
            gap_repaired=is_repaired,
            repair_reason=repair.reason,
        )
        if mode == "acknowledge":
            reply = ACKNOWLEDGE_REPLY[student_language(request.student_text)]
            view = ReplyCheckView(approved=True, summary="No teaching move needed; fixed acknowledgement.")
        else:
            reply, view = await self._teach_and_verify(request, diagnosis, mode, step, strategy, trace)

        output = TutorTeachingOutput(**diagnosis.model_dump(), gap_repaired=is_repaired, reply=reply)
        return TeachResult(output=output, method=strategy, reply_check=view), trace

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
            mode=mode, # type: ignore
            diagnosis=diagnosis,
            gap_step=step,
            strategy=strategy,
            method_definition=METHOD_DEFINITIONS[strategy.method] if strategy else None,
            method_guidance=GUIDANCE[strategy.method] if strategy else None,
            hints_used=request.hints_used,
            solution_steps=request.solution.steps,
            language=student_language(request.student_text),
        )
        for _ in range(1 + MAX_REGENERATIONS):
            written = await write_reply(teaching_input, self._model, self._timeout)
            if not written.ok:
                trace.drafts.append(Draft(reply="", failure=f"teaching: {written.failure}: {written.detail}")) # type: ignore
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
                    main_gap=diagnosis.main_gap,
                    gap_step=_describe(step),
                    error_mismatch=diagnosis.error.mismatch if diagnosis.error else None,
                    method_definition=METHOD_DEFINITIONS[strategy.method] if strategy else None,
                    language=teaching_input.language,
                ),
                self._verifier_model,
                final_answers(request.solution),
                self._timeout,
            )
            if not checked.ok:
                # Never send an unchecked reply.
                trace.drafts.append(Draft(reply=reply, failure=f"verifier: {checked.failure}: {checked.detail}")) # type: ignore
                break
            check = checked.value
            trace.drafts.append(Draft(reply=reply, check=check))
            if check.approved:
                return reply, ReplyCheckView(approved=True, summary=check.note)
            teaching_input = teaching_input.model_copy(update={"retry_reason": check.reason, "retry_note": check.note})
        trace.fallback = True
        return FALLBACK_REPLY[teaching_input.language], ReplyCheckView(approved=False, summary="Safe fallback used.")
