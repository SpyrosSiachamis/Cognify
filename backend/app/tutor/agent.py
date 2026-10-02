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

import logging
import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai.models import Model

from app.ai_gateway import gateway
from app.common import trace as session_trace
from app.history import HistoryStore
from app.session.schema import Solution
from app.session.schema import Solution as SessionSolution
from app.user.ports import (
    DraftOutcome,
    FollowUpRequest,
    FollowUpResult,
    JudgeRequest,
    ProblemSetup,
    TeachRequest,
    TeachResult,
)
from app.verification.agent import check_reply, check_student, demonstrated_answers, leaked_answer
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
from .fallback import explain_fallback
from .language import ACKNOWLEDGE_REPLY, STRESS_TEST_MESSAGE, student_language, written_in
from .methods import GUIDANCE, METHOD_DEFINITIONS
from .teaching import write_reply

log = logging.getLogger(__name__)

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


# The cause of a fallback is the last draft's outcome (earlier drafts are in the draft records).
FALLBACK_SUMMARY = {
    "verifier_rejected": "Safe fallback used: the verifier rejected the last draft",
    "teaching_failed": "Safe fallback used: the teaching step returned no usable draft",
    "verifier_error": "Safe fallback used: the verifier could not check the last draft, so it was not sent",
    "wrong_language": "Safe fallback used: the last draft was in the wrong language",
}


def draft_outcome(draft: "Draft", strategy: ChooseStrategyResult | None) -> DraftOutcome:
    """One draft's fate in the telemetry vocabulary (the failure prefixes are set in _teach_and_verify)."""
    method = strategy.method if strategy else None
    if draft.check is not None:
        if draft.check.approved:
            return DraftOutcome(outcome="approved", note=draft.check.note, method=method)
        return DraftOutcome(outcome="verifier_rejected", reason=draft.check.reason, note=draft.check.note, method=method)
    failure = draft.failure or ""
    kind = ("wrong_language" if failure.startswith("language") else
            "verifier_error" if failure.startswith("verifier") else "teaching_failed")
    return DraftOutcome(outcome=kind, note=failure, method=method)


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
    if diagnosis.response_to != "original_problem" and not any(s.status == "wrong" for s in diagnosis.steps):
        # A right answer to part of the problem is not the whole solution: keep teaching the open gap.
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
            reply_check=ReplyCheckView(approved=True, summary=check.note, outcome="approved"),
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
            ReasoningInput(
                problem=request.problem, attempt=request.student_text, final_answer=request.solution.result,
                tutor_message=request.tutor_message,
            ),
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
        # (A right answer to part of the problem arrives here with no gap: the rules clear a gap when every step it
        # kept is correct, so the gap being taught is carried, never one the model guessed from the partial answer.)
        carried = mode == "teach" and diagnosis.main_gap is None
        if carried:
            diagnosis = carry_gap(diagnosis, prior_gap)
        partial = diagnosis.evidence == "insufficient" or (
            diagnosis.response_to != "original_problem" and not any(s.status == "wrong" for s in diagnosis.steps)
        )
        step = gap_step(prior.steps if partial and prior else diagnosis.steps, diagnosis.main_gap)
        strategy = (
            choose_strategy(self._store, request.student_id, diagnosis.main_gap, request.force_experiment)
            if mode == "teach" and diagnosis.main_gap is not None
            else None
        )
        if session_trace.active():
            with session_trace.guard():
                session_trace.record(
                    session_trace.DiagnosisResult,
                    kind="initial" if request.first_thought else "repair" if prior_gap else "follow_up",
                    main_gap=diagnosis.main_gap, alternatives=[a.gap for a in diagnosis.alternatives],
                    confidence=diagnosis.confidence, evidence=diagnosis.evidence, response_to=diagnosis.response_to,
                    diagnosis_failed=None if reasoned.ok else reasoned.failure, prior_gap=prior_gap,
                    gap_carried=carried and diagnosis.main_gap is not None, gap_repaired=is_repaired,
                    repair_reason=repair.reason, mode=mode, gap_step=step,
                    method=strategy.method if strategy else None, decision_mode=strategy.mode if strategy else None,
                    strategy_reason=strategy.reason if strategy else None,
                    strategy_uses=strategy.evidence.uses if strategy else None,
                    strategy_independent_successes=strategy.evidence.independent_successes if strategy else None,
                    diagnosis=diagnosis,
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
            view = ReplyCheckView(
                approved=True, summary="No teaching move needed; fixed acknowledgement.", outcome="fixed_reply"
            )
        else:
            reply, view = await self._teach_and_verify(request, diagnosis, mode, step, strategy, trace)

        drafts = [draft_outcome(d, strategy) for d in trace.drafts]
        for i, d in enumerate(drafts):
            log.info("teaching draft %d: %s%s%s", i + 1, d.outcome, f" ({d.reason})" if d.reason else "",
                     f": {d.note}" if d.note else "")
        output = TutorTeachingOutput(**diagnosis.model_dump(), gap_repaired=is_repaired, reply=reply)
        # A method counts as used only when its reply reached the student: a fallback shows and credits none.
        delivered = strategy if view.outcome == "approved" else None
        return TeachResult(output=output, method=delivered, reply_check=view, drafts=drafts), trace

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
        steps = list(request.earlier_correct_steps)
        if not any(s.status == "wrong" for s in diagnosis.steps):
            steps += diagnosis.steps
        shown, unlocked = demonstrated_answers(
            [(s.role, s.status, s.quote) for s in steps], final_answers(request.solution), request.problem
        )
        withheld = [a for a in final_answers(request.solution) if a not in unlocked]
        method = strategy.method if strategy else None
        for attempt in range(1, 2 + MAX_REGENERATIONS):
            session_trace.record(
                session_trace.TeachingGenerationStarted, attempt=attempt, mode=mode, method=method,
                main_gap=diagnosis.main_gap, gap_step=step, retry_reason=teaching_input.retry_reason,
                retry_note=teaching_input.retry_note, language=teaching_input.language,
                hints_used=request.hints_used, problem=request.problem,
            )
            written = await write_reply(teaching_input, self._model, self._timeout)
            if not written.ok:
                trace.drafts.append(Draft(reply="", failure=f"teaching: {written.failure}: {written.detail}")) # type: ignore
                session_trace.record(
                    session_trace.TeachingGenerationResult, attempt=attempt, outcome="teaching_failed", draft=None,
                    failure=written.failure, detail=written.detail, model=self._model.model_name,  # type: ignore
                )
                break
            reply = written.value.reply
            if not written_in(reply, teaching_input.language):
                # Code check: the wrong language never reaches the verifier or the student.
                trace.drafts.append(Draft(reply=reply, failure=f"language: not written in {teaching_input.language}"))
                session_trace.record(
                    session_trace.TeachingGenerationResult, attempt=attempt, outcome="wrong_language", draft=reply,
                    failure=None, detail=f"not written in {teaching_input.language}", model=self._model.model_name,
                )
                teaching_input = teaching_input.model_copy(update={
                    "retry_reason": None,
                    "retry_note": f"Your reply was not in {teaching_input.language}. Write it entirely in "
                    f"{teaching_input.language}, the student's language.",
                })
                continue
            session_trace.record(
                session_trace.TeachingGenerationResult, attempt=attempt, outcome="draft", draft=reply, failure=None,
                model=self._model.model_name,
            )
            check_input = ReplyCheckInput(
                problem=request.problem,
                attempt=request.student_text,
                reply=reply,
                method=method,
                hints_used=request.hints_used,
                hidden_solution=" ".join(request.solution.steps),
                main_gap=diagnosis.main_gap,
                gap_step=_describe(step),
                error_mismatch=diagnosis.error.mismatch if diagnosis.error else None,
                method_definition=METHOD_DEFINITIONS[strategy.method] if strategy else None,
                language=teaching_input.language,
                student_demonstrated=shown,
            )
            checked = await check_reply(check_input, self._verifier_model, withheld, self._timeout)
            if session_trace.active():
                with session_trace.guard():
                    session_trace.record(
                        session_trace.VerifierResult, attempt=attempt,
                        checker="code_leak_check" if leaked_answer(reply, withheld) else "model",
                        outcome="verifier_error" if not checked.ok
                        else "approved" if checked.value.approved else "verifier_rejected",
                        reason=checked.value.reason if checked.ok else None,
                        note=checked.value.note if checked.ok else f"{checked.failure}: {checked.detail}",  # type: ignore
                        method=method, main_gap=diagnosis.main_gap, gap_step=check_input.gap_step, draft=reply,
                        student_demonstrated=shown, withheld_answers=withheld,
                    )
            if not checked.ok:
                # Never send an unchecked reply.
                trace.drafts.append(Draft(reply=reply, failure=f"verifier: {checked.failure}: {checked.detail}")) # type: ignore
                break
            check = checked.value
            trace.drafts.append(Draft(reply=reply, check=check))
            if check.approved:
                return reply, ReplyCheckView(approved=True, summary=check.note, outcome="approved")
            teaching_input = teaching_input.model_copy(update={"retry_reason": check.reason, "retry_note": check.note})
        trace.fallback = True
        last = draft_outcome(trace.drafts[-1], strategy) if trace.drafts else None
        outcome = last.outcome if last else "teaching_failed"
        # Say why another answer is needed, from this turn's diagnosis (code only; it quotes only the student).
        fallback, explanation = explain_fallback(
            diagnosis, step, request.student_text, teaching_input.language, request.tutor_message
        )
        if session_trace.active():
            with session_trace.guard():
                outcomes = [draft_outcome(d, strategy) for d in trace.drafts]
                session_trace.record(
                    session_trace.TeachingFallback, attempts=len(trace.drafts), last_outcome=outcome,
                    last_reason=last.reason if last else None,
                    drafts=[{"attempt": i + 1, "outcome": o.outcome, "reason": o.reason, "note": o.note,
                             "draft": d.reply or None} for i, (d, o) in enumerate(zip(trace.drafts, outcomes))],
                    fallback_reply=fallback, explanation=explanation,
                    evidence_unrecognized=explanation == "unrecognized_evidence", main_gap=diagnosis.main_gap,
                    method=method, counts_as_hint=False,
                )
        # The summary goes to the browser: the outcome and the verifier's reason only, never raw failure text (that
        # stays in the draft records and the log).
        return fallback, ReplyCheckView(
            approved=False, summary=FALLBACK_SUMMARY[outcome] + (f" ({last.reason})" if last and last.reason else ""),
            outcome=outcome,
        )
