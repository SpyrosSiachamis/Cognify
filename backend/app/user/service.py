import asyncio
import contextvars
import hashlib
import json
import logging
import re
from collections.abc import Awaitable
from uuid import UUID

from app.common import trace as session_trace
from app.common.vocab import GapType, NotYetReason, State, Strategy
from app.history import HistoryStore
from app.history import schema as rec
from app.tutor.schema import EvidenceCounts, FollowUpDraft, PriorDiagnosis, Step
from app.user.errors import ApiError
from app.user.ports import (
    FollowUpRequest,
    FollowUpResult,
    JudgeRequest,
    TeachRequest,
    TutorPort,
)
from app.session.schema import (
    AttemptResponse,
    ConceptChange,
    ExitResponse,
    SessionStartRequest,
    SessionStartResponse,
    Solution,
    StrategyChange,
    Verdict,
    VerdictChanges,
    VerdictTurn,
)
from app.tutor.schema import DiagnosisView, FollowUpView, MethodView, ReplyCheckView, TutorTurn
from app.user.schema import (
    LearnerConcept,
    LearnerView,
    MethodTotal,
    SessionTraceView,
    StrategyRow,
    StrategyView,
    TraceExport,
    TraceIndex,
    TraceSummary,
)

log = logging.getLogger(__name__)

# Every this many teaching turns of a cycle with the problem still unresolved, the student is offered the choice to
# stop. It is never a move to the fresh problem: only a resolved problem removes support.
MAX_TEACH_TURNS = 4
MAX_NOT_YET = 2  # the second NOT YET ends the session
MAX_HINTS_FOR_VERIFIED = 2  # a correct answer after more hints than this is a lucky one (F16)
MAX_FOLLOW_UP_TRIES = 3  # a repeated follow-up is regenerated this many times, then we give up
# Time budgets for everything the agent does inside one request, kept under what the frontend waits
# (120 s to start, 240 s per turn). A real turn chains a diagnosis, up to 3 write-and-check rounds and a
# follow-up, so one short limit per call would throw away a slow turn that is still working.
START_BUDGET_SECONDS = 100.0
TURN_BUDGET_SECONDS = 200.0

FIRST_THOUGHT_PROMPT = "Before I help, what would you try first? Even an incomplete idea is useful."
EMPTY_PROBE = "What is one thing you notice in the problem?"
EMPTY_STRESS_TEST = "Take your time. Write what you would try, even if it is not finished."
SAFE_FALLBACK = "What would you try next?"
OFFER_EXIT = ("We have been on this for a while. You can keep working on this step with me, or press Exit to see the "
              "full solution.")


def fingerprint(text: str) -> str:
    """Normalised text hash. Placeholder: the novelty module should own this."""
    normalised = " ".join(re.sub(r"[^\w\s]", "", text.lower()).split())
    return hashlib.sha256(normalised.encode()).hexdigest()


def _internal(message: str) -> ApiError:
    return ApiError(500, "internal_error", message)


def _unavailable() -> ApiError:
    return ApiError(503, "model_unavailable", "Please try again.", retryable=True)


class SessionService:
    """Owns the Master flow: phases, hint counts, caps and the VERIFIED decision.
    The agent only reasons and writes; it never moves the session along."""

    def __init__(
        self, tutor: TutorPort, store: HistoryStore, timeout: float | None = None, tracing: bool | None = None,
    ) -> None:
        """`timeout` replaces both budgets (the tests use a short one)."""
        self._tutor = tutor
        self._store = store
        self._start_budget = START_BUDGET_SECONDS if timeout is None else timeout
        self._turn_budget = TURN_BUDGET_SECONDS if timeout is None else timeout
        self._deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar("deadline", default=None)
        # Sessions whose gap is repaired but whose follow-up could not be made yet, with the gap to build it from
        self._follow_up_owed: dict[UUID, GapType | None] = {}
        # The development session trace (DEBUG_TRACE): recorded and saved through history; never read by the flow.
        self.tracing = session_trace.enabled() if tracing is None else tracing
        self._locks: dict[UUID, asyncio.Lock] = {}  # one turn at a time per session (a double click)

    def _begin_budget(self, seconds: float) -> None:
        self._deadline.set(asyncio.get_running_loop().time() + seconds)

    async def _ask[T](self, call: Awaitable[T]) -> T:
        """Every call to the agent runs inside the request's time budget; the caller turns any failure
        into a fallback."""
        deadline = self._deadline.get()
        remaining = None if deadline is None else deadline - asyncio.get_running_loop().time()
        if remaining is not None and remaining <= 0:
            if asyncio.iscoroutine(call):
                call.close()  # never started, so nothing to cancel
            raise TimeoutError("the time budget for this request is used up")
        return await asyncio.wait_for(call, remaining)

    def _lock(self, session_id: UUID) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    def _forget_lock(self, session_id: UUID) -> None:
        """Drop the lock of a session that is over or never existed, so ids cannot pile up."""
        session = self._store.get_session(session_id)
        if session is None or session.status != "active":
            self._locks.pop(session_id, None)
            self._follow_up_owed.pop(session_id, None)

    # ---- start and exit ----

    async def start(self, req: SessionStartRequest) -> SessionStartResponse:
        with session_trace.collecting(self.tracing) as buffer:
            session: rec.Session | None = None
            try:
                session = await self._start(req)
                return SessionStartResponse(
                    session_id=session.id, phase=session.phase, message=FIRST_THOUGHT_PROMPT, hints_used=0
                )
            finally:
                self._save_trace(session.id if session else None, buffer)

    async def _start(self, req: SessionStartRequest) -> rec.Session:
        if self._store.get_student(req.student_id) is None:
            raise ApiError(404, "unknown_student", "No learner with that id.")
        self._begin_budget(self._start_budget)
        try:
            setup = await self._ask(self._tutor.set_up(req.problem, req.subject))
        except Exception as exc:  # a bad agent reply must never become a 500 (F25)
            log.warning("tutor set_up failed", exc_info=True)
            error = _unavailable()
            session_trace.record_error("start", error, cause=exc)
            raise error from exc
        concept = self._store.get_or_create_concept(setup.concept_name)
        problem = self._store.add_problem(
            rec.Problem(text=req.problem, subject=req.subject, fingerprint=fingerprint(req.problem))
        )
        session = self._store.create_session(
            rec.Session(
                student_id=req.student_id,
                problem_id=problem.id,
                concept_id=concept.id,
                force_experiment=req.force_experiment,
                hidden_solution=rec.SessionSolution(**setup.solution.model_dump()),
            )
        )
        session_trace.record(
            session_trace.SessionStarted, student_id=session.student_id, problem_id=problem.id, problem=req.problem,
            subject=req.subject, concept_id=concept.id, concept_name=concept.name,
            concept_state=self._concept_state(session), phase=session.phase, force_experiment=session.force_experiment,
            solution_result=setup.solution.result,
        )
        return session

    async def exit(self, session_id: UUID) -> ExitResponse:
        try:
            async with self._lock(session_id):  # wait for a turn that is still running
                session = self._open(session_id)
                with session_trace.collecting(self.tracing) as buffer:
                    try:
                        if session.hidden_solution is None:
                            raise _internal("Session has no solution.")
                        previous = session.phase
                        session.phase = "exited"
                        session.status = "exited"
                        session.ended_at = rec.now()
                        self._store.update_session(session)  # no outcome is written: exit records no evidence
                        if buffer is not None:
                            with session_trace.guard():
                                self._trace_transition(session, previous, "exit")
                                self._trace_end(session, "exit")
                        return ExitResponse(
                            phase="exited",
                            solution=Solution(**session.hidden_solution.model_dump()),
                            evidence_recorded=False,
                        )
                    except Exception as exc:
                        if not session_trace.already_recorded(exc):
                            session_trace.record_error("exit", exc)
                        raise
                    finally:
                        self._save_trace(session_id, buffer)
        finally:
            self._forget_lock(session_id)

    # ---- the turn endpoint ----

    async def attempt(self, session_id: UUID, text: str) -> AttemptResponse:
        try:
            async with self._lock(session_id):  # the state is read inside the lock, after any turn ahead of us
                session = self._open(session_id)
                self._begin_budget(self._turn_budget)
                with session_trace.collecting(self.tracing) as buffer:
                    try:
                        if buffer is not None:
                            with session_trace.guard():
                                self._trace_response(session, text)
                        if session_id in self._follow_up_owed:
                            # The gap was repaired but the follow-up failed last time. Do not teach again (that
                            # would cost another hint for the model's failure): just make the follow-up.
                            # Owed only after a resolved problem (see _teach), so the invariant still holds.
                            return await self._stress_test(session, self._follow_up_owed[session_id], resolved=True)
                        if not text.strip():
                            # Never explain instead of asking; nothing is saved and the agent is not called
                            return self._blank_turn(session)
                        if session.phase == "stress_test":
                            return await self._judge(session, text)
                        return await self._teach(session, text)
                    except Exception as exc:
                        if not session_trace.already_recorded(exc):
                            session_trace.record_error("attempt", exc)
                        raise
                    finally:
                        self._save_trace(session_id, buffer)  # inside the lock: turns are saved in order
        finally:
            self._forget_lock(session_id)

    async def _teach(self, session: rec.Session, text: str) -> TutorTurn:
        concept = self._concept(session)
        first = session.phase == "ask_first_thought"
        # One hint for the previous reply only if it was an approved teaching move that reached the student
        # (F16). Fallbacks, probes, acknowledgements and the fixed prompts are not help.
        hints = session.hints_used + (1 if session.last_reply_taught else 0)
        turns = session.teach_turns + 1
        problem, solution = self._teaching_problem(session)
        request = TeachRequest(
            student_id=session.student_id,
            problem=problem,
            concept_name=concept.name,
            solution=solution,
            student_text=text,
            first_thought=first,
            hints_used=hints,
            teach_turns=turns,
            force_experiment=session.force_experiment,
            after_not_yet=session.not_yet_count > 0 and session.teach_turns == 0,
            prior=self._prior(session),
            tutor_message=session.last_tutor_message,
            earlier_correct_steps=self._earlier_correct_steps(session),
            validated_steps=self._earlier_correct_steps(session, also_with_wrong=True),
        )
        try:
            result = await self._ask(self._tutor.teach(request))
        except Exception as exc:
            log.warning("tutor teach failed; sent the safe fallback (session %s)", session.id, exc_info=True)
            session_trace.record_error("teach", exc, handled=True)
            session_trace.record(
                session_trace.ReplySent, kind="turn_failed", message=SAFE_FALLBACK, reply_outcome="turn_failed",
                method=None, shown_to_student=True, counts_as_hint=False,
            )
            # Nothing of this turn is counted or changed: a hint owed for an earlier delivered move stays owed, and
            # the outstanding tutor message stays as context (the student will likely resend the same answer).
            return self._turn(session, SAFE_FALLBACK, ReplyCheckView(
                approved=False, summary="Safe fallback used: the turn failed before a reply was ready.",
                outcome="turn_failed",
            ))

        out, method = result.output, result.method
        attempt = rec.Attempt(session_id=session.id, phase=session.phase, text=text, response_to=out.response_to)
        steps = [
            rec.AttemptStep(attempt_id=attempt.id, position=i, role=s.role, status=s.status, quote=s.quote)
            for i, s in enumerate(out.steps)
        ]
        self._store.add_attempt(attempt, steps)
        self._store.add_diagnosis(
            rec.Diagnosis(
                attempt_id=attempt.id,
                main_gap=out.main_gap,
                alternatives=[rec.AlternativeGap(**a.model_dump()) for a in out.alternatives],
                confidence=out.confidence,
                dimensions=[rec.DimensionRating(**d.model_dump()) for d in out.dimensions],
            )
        )
        self._store.add_reply_drafts([
            rec.ReplyDraft(session_id=session.id, attempt_id=attempt.id, position=i, outcome=d.outcome,
                           reason=d.reason, note=d.note, method=d.method)
            for i, d in enumerate(result.drafts)
        ])

        # The invariant: support is removed (and a fresh problem starts) only when the problem is resolved by the
        # student's own demonstrated work, as code read it (TutorTeachingOutput.resolution). Never because no error was
        # found, a taught step alone was fixed, or a number of turns went by.
        moving_on = out.resolution == "PROBLEM_RESOLVED"
        # A long unresolved cycle offers the student the choice to stop; tutoring goes on (the reply is code-written
        # and carries nothing about the problem).
        offer_exit = not moving_on and turns % MAX_TEACH_TURNS == 0
        reply = f"{out.reply}\n\n{OFFER_EXIT}" if offer_exit else out.reply
        # A teaching move is delivered only if its approved reply is the one the student sees: not a fallback
        # (the agent then reports no method) and not a reply replaced by the stress test.
        delivered = not moving_on and method is not None and result.reply_check.outcome == "approved"
        # The app records the tool's result; what history credits never comes from the model's wording.
        # Only a delivered move is recorded: a probe, an acknowledgement or a fallback taught nothing.
        if delivered and out.main_gap is not None:
            self._store.add_strategy_decision(
                rec.StrategyDecision(
                    session_id=session.id,
                    gap_type=out.main_gap,
                    method=method.method,
                    decision_mode=method.mode,
                    reason=method.reason,
                    uses=method.evidence.uses,
                    independent_successes=method.evidence.independent_successes,
                )
            )
        session.phase = "teach"
        session.hints_used = hints
        session.teach_turns = turns
        session.last_reply_taught = delivered
        if not moving_on:
            # The context is the reply the student sees, whatever it is (a probe or a fallback too): the next answer
            # is an answer to it. Hint counting is separate (last_reply_taught). On the way to the fresh problem the
            # context is kept until the follow-up is stored (_stress_test), so a retry after a failed follow-up
            # still reads the answer against the question it answered.
            session.last_tutor_message = reply
        self._store.update_session(session)

        tracing = session_trace.active()
        if tracing and first:
            with session_trace.guard():
                self._trace_transition(session, "ask_first_thought", "first_answer")
        if moving_on:
            reason = "problem_resolved"
            if tracing:
                with session_trace.guard():
                    decision = self._cycle_decision(session)
                    practice = session.active_practice_problem
                    session_trace.record(
                        session_trace.SupportRemoved, reason=reason, problem_id=session.problem_id,
                        practice_follow_up_id=practice.follow_up_id if practice else None, main_gap=out.main_gap,
                        method=decision.method if decision else None, concept_state=self._concept_state(session),
                        replaced_reply=out.reply, counters=self._counters(session),
                    )
            self._follow_up_owed[session.id] = out.main_gap  # cleared once the follow-up exists
            turn = await self._stress_test(session, out.main_gap, resolved=True)
            if tracing:
                with session_trace.guard():
                    self._trace_transition(session, "teach", reason)
            return turn
        if tracing:
            with session_trace.guard():
                kind = ("safe_fallback" if result.reply_check.outcome not in ("approved", "fixed_reply")
                        else "acknowledgement" if result.reply_check.outcome == "fixed_reply"
                        else "teaching" if method is not None else "probe")
                session_trace.record(
                    session_trace.ReplySent, kind=kind, message=reply, reply_outcome=result.reply_check.outcome,
                    unresolved_policy="offer_exit" if offer_exit else None,
                    method=method.method if delivered and method else None, shown_to_student=True,
                    counts_as_hint=delivered,
                )
        return TutorTurn(
            session_id=session.id,
            phase="teach",
            message=reply,
            diagnosis=DiagnosisView(
                steps=out.steps, main_gap=out.main_gap, alternatives=out.alternatives, confidence=out.confidence
            ),
            method=None
            if not delivered or method is None
            else MethodView(
                name=method.method, mode=method.mode, experiment=method.mode == "experiment", reason=method.reason
            ),
            hints_used=session.hints_used,
            reply_check=result.reply_check,
        )

    async def _stress_test(self, session: rec.Session, main_gap: GapType | None, resolved: bool) -> TutorTurn:
        if not resolved:
            # The invariant, kept where the transition happens: no fresh problem without a resolved one.
            raise _internal("Support can only be removed once the problem is resolved by the student's own work.")
        result, new_fingerprint = await self._new_follow_up(session, main_gap)
        draft = result.output.follow_up
        saved = self._store.add_follow_up(
            rec.FollowUp(
                session_id=session.id,
                problem_text=draft.problem,
                fingerprint=new_fingerprint,
                concept_invariant=draft.concept_invariant,
                target_gap=draft.target_gap,
                target_step=draft.target_step,
                perturbation=draft.perturbation,
                difficulty=draft.difficulty,
                hidden_rubric=draft.hidden_rubric,
            )
        )
        session.phase = "stress_test"
        session.last_tutor_message = None  # the answer to the fresh problem is judged, not diagnosed
        session.active_practice_problem = None  # a repaired practice problem is closed; the new one is fresh
        self._store.update_session(session)
        self._follow_up_owed.pop(session.id, None)
        if session_trace.active():
            with session_trace.guard():
                session_trace.record(
                    session_trace.FreshProblemGenerated, follow_up_id=saved.id, problem_id=session.problem_id,
                    problem=draft.problem, concept_invariant=draft.concept_invariant, target_gap=draft.target_gap,
                    target_step=draft.target_step, perturbation=draft.perturbation, difficulty=draft.difficulty,
                    fingerprint=new_fingerprint, support_removed=True, hints_available=False,
                )
                session_trace.record(
                    session_trace.ReplySent, kind="fresh_problem", message=result.message, reply_outcome="approved",
                    method=None, shown_to_student=True, counts_as_hint=False,
                )
        return TutorTurn(
            session_id=session.id,
            phase="stress_test",
            message=result.message,
            follow_up=FollowUpView(problem=draft.problem),  # the rubric stays on the backend
            hints_used=session.hints_used,
            reply_check=result.reply_check,
        )

    async def _new_follow_up(self, session: rec.Session, main_gap: GapType | None) -> tuple[FollowUpResult, str]:
        """Ask for a follow-up and regenerate while it repeats something this student has seen."""
        seen = {s.fingerprint for s in self._store.seen_fingerprints(session.student_id)}
        retry_reason: str | None = None
        for number in range(1, MAX_FOLLOW_UP_TRIES + 1):
            try:
                request = FollowUpRequest(
                    student_id=session.student_id,
                    problem=self._problem_text(session),
                    concept_name=self._concept(session).name,
                    solution=self._solution(session),
                    main_gap=main_gap,
                    hints_used=session.hints_used,
                    retry_reason=retry_reason,
                    **self._follow_up_evidence(session),
                )
                session_trace.record(
                    session_trace.FollowUpStarted, request=number, reason="support_removed", retry_reason=retry_reason,
                    problem_id=session.problem_id, main_gap=main_gap, method=request.method,
                    hints_used=session.hints_used, last_steps=request.last_steps,
                )
                result = await self._ask(self._tutor.follow_up(request))
            except Exception as exc:
                log.warning("tutor follow_up failed (session %s)", session.id, exc_info=True)
                error = _unavailable()
                session_trace.record_error("follow_up", error, cause=exc)
                raise error from exc
            new_fingerprint = fingerprint(result.output.follow_up.problem)
            if new_fingerprint not in seen:
                return result, new_fingerprint
            session_trace.record(session_trace.FollowUpResult, attempt=0, outcome="already_seen",
                                 note="The session's freshness check: the student has already seen this problem.",
                                 draft=result.output.follow_up)
            retry_reason = "The student has already seen this problem."
        error = _unavailable()
        session_trace.record_error("follow_up", error, cause=RuntimeError("every follow-up repeated a seen problem"))
        raise error

    async def _judge(self, session: rec.Session, text: str) -> VerdictTurn:
        follow_up = self._store.latest_follow_up(session.id)
        diagnosis = self._store.latest_diagnosis(session.id)
        decision = self._cycle_decision(session)
        if follow_up is None or diagnosis is None:
            raise _internal("Session is missing its follow-up or diagnosis.")
        concept = self._concept(session)
        try:
            request = JudgeRequest(
                problem=self._problem_text(session),
                solution=self._solution(session),
                follow_up=FollowUpDraft(
                    problem=follow_up.problem_text,
                    concept_invariant=follow_up.concept_invariant,
                    target_gap=follow_up.target_gap,
                    target_step=follow_up.target_step,
                    perturbation=follow_up.perturbation,
                    difficulty=follow_up.difficulty,
                    hidden_rubric=follow_up.hidden_rubric,
                ),
                student_text=text,
                hints_used=session.hints_used,
            )
            check = await self._ask(self._tutor.judge(request))
        except Exception as exc:
            log.warning("tutor judge failed (session %s)", session.id, exc_info=True)
            error = _unavailable()
            session_trace.record_error("judge", error, cause=exc)
            raise error from exc

        # Code decides VERIFIED: the verifier's judgement, the hint count, and a fresh problem
        independent = check.own_work and session.hints_used <= MAX_HINTS_FOR_VERIFIED
        verified = check.correct and independent
        # Why not, when not: only incorrect and not_own_work are evidence that the student could not do it.
        reason: NotYetReason | None = (
            None if verified else "incorrect" if not check.correct else "not_own_work" if not check.own_work
            else "hint_limit"
        )
        # Credit goes to the method delivered in this teaching cycle; a cycle that taught nothing credits none.
        gap = decision.gap_type if decision else None
        method = decision.method if decision else None
        before_state = self._concept_state(session)
        after_state = self._next_state(before_state, verified, reason)
        before_counts = self._counts(session.student_id, gap, method) if gap and method else None
        over = verified or session.not_yet_count + 1 >= MAX_NOT_YET
        # After a first NOT YET the repair cycle teaches on the failed fresh problem, so it needs that problem's own
        # answer: solved here with the session's set-up step, before anything is written.
        practice = None if over else await self._practice_problem(follow_up)
        # Built (and so validated) before anything is written: a bad outcome must not leave half a verdict.
        outcome = rec.Outcome(
            student_id=session.student_id,
            session_id=session.id,
            concept_id=concept.id,
            gap_type=gap,
            method=method,
            decision_mode=decision.decision_mode if decision else None,
            result="VERIFIED" if verified else "NOT YET",
            not_yet_reason=reason,
            independent=independent,
            hints_used=session.hints_used,
            concept_before=before_state,
            concept_after=after_state,
            evidence=check.note,
            remaining_gap=None if verified else gap,
        )

        self._store.add_attempt(rec.Attempt(session_id=session.id, phase="stress_test", text=text), [])
        self._store.add_verifier_check(
            rec.VerifierCheck(
                session_id=session.id,
                mode="student_check",
                approved=check.own_work,
                reason=None if check.own_work else "not_independent",
                note=check.note,
                correct=check.correct,
                reasoning_quality=check.reasoning_quality,
                own_work=check.own_work,
            )
        )

        self._store.record_verdict(outcome, session_over=over)
        # record_verdict moved the session to the verdict phase; after a first NOT YET it goes back to teaching
        session = self._store.get_session(session.id) or session
        if not verified:
            session.not_yet_count += 1
        if verified:
            message = "You solved it on your own."
        elif over:
            message = f"Not yet, and that is okay. What we learned: {check.note} You can exit when you like."
        else:
            message = "Not yet. Here is what we will try differently."
        if not over:
            session.phase = "teach"
            session.teach_turns = 0
            # The repair cycle works on the practice problem just answered (the student still sees it); the original
            # problem stays the session's problem. A verdict is not a teaching move, so no hint is owed for it.
            session.active_practice_problem = practice
            session.last_reply_taught = False
            session.last_tutor_message = message
        self._store.update_session(session)
        after_counts = self._counts(session.student_id, gap, method) if gap and method else None
        if session_trace.active():
            with session_trace.guard():
                session_trace.record(
                    session_trace.TransferResult, problem_id=session.problem_id, follow_up_id=follow_up.id,
                    problem=self._problem_text(session), fresh_problem=follow_up.problem_text, concept_id=concept.id,
                    concept_name=concept.name, support_removed=True, hints_used=outcome.hints_used, student_text=text,
                    correct=check.correct, own_work=check.own_work, reasoning_quality=check.reasoning_quality,
                    judge_note=check.note, verified=verified, independent=independent, not_yet_reason=reason,
                    concept_before=before_state, concept_after=after_state, gap_credited=gap, method_credited=method,
                    decision_mode=outcome.decision_mode,
                    strategy_uses_before=before_counts.uses if before_counts else None,
                    strategy_independent_successes_before=before_counts.independent_successes if before_counts else None,
                    strategy_uses_after=after_counts.uses if after_counts else None,
                    strategy_independent_successes_after=after_counts.independent_successes if after_counts else None,
                    session_over=over,
                    practice_follow_up_id=session.active_practice_problem.follow_up_id
                    if session.active_practice_problem else None,
                )
                session_trace.record(
                    session_trace.ReplySent, kind="verdict", message=message, reply_outcome=None, method=None,
                    shown_to_student=True, counts_as_hint=False,
                )
                self._trace_transition(
                    session, "stress_test", "verified" if verified else "not_yet_final" if over else "not_yet"
                )
                if over:
                    self._trace_end(session, "verified" if verified else "not_yet_cap")
        return VerdictTurn(
            session_id=session.id,
            phase="verdict",
            session_over=over,
            message=message,
            verdict=Verdict(
                result="VERIFIED" if verified else "NOT YET",
                evidence=check.note,
                independent=independent,
                remaining_gap=None if verified else gap,
                changes=VerdictChanges(
                    concept=ConceptChange(
                        concept_id=concept.id, name=concept.name, before=before_state, after=after_state
                    ),
                    strategy=None
                    if gap is None or method is None or before_counts is None
                    else StrategyChange(
                        gap=gap, method=method, before=before_counts, after=after_counts  # type: ignore[arg-type]
                    ),
                ),
            ),
        )

    # ---- the two learner views ----

    def learner_view(self, student_id: UUID) -> LearnerView:
        student = self._student(student_id)
        concepts = []
        for state in self._store.list_concept_states(student_id):
            concept = self._store.get_concept(state.concept_id)
            if concept is not None:
                concepts.append(
                    LearnerConcept(
                        concept_id=concept.id, name=concept.name, state=state.state, evidence=state.evidence
                    )
                )
        return LearnerView(
            student_id=student.id, display_name=student.display_name, is_seeded=student.is_seeded, concepts=concepts
        )

    def strategy_view(self, student_id: UUID) -> StrategyView:
        student = self._student(student_id)
        stats = self._store.strategy_stats(student_id)
        totals: dict[Strategy, list[int]] = {}
        for s in stats:
            total = totals.setdefault(s.method, [0, 0])
            total[0] += s.uses
            total[1] += s.independent_successes
        return StrategyView(
            student_id=student.id,
            display_name=student.display_name,
            is_seeded=student.is_seeded,
            rows=[
                StrategyRow(
                    gap=s.gap_type, method=s.method, uses=s.uses,
                    independent_successes=s.independent_successes, experiments=s.experiments,
                )
                for s in stats
            ],
            methods=[MethodTotal(method=m, uses=u, independent_successes=w) for m, (u, w) in totals.items()],
        )

    # ---- the development session trace (read-only views of the flow; never changes it) ----

    def trace_view(self, session_id: UUID) -> SessionTraceView:
        if self._store.get_session(session_id) is None:
            raise ApiError(404, "unknown_session", "No session with that id.")
        return SessionTraceView(session_id=session_id, events=self._store.list_trace_events(session_id))

    def trace_index(self) -> TraceIndex:
        rows = []
        for session_id in self._store.traced_sessions():
            session = self._store.get_session(session_id)
            if session is None:
                continue
            rows.append(TraceSummary(
                session_id=session.id, student_id=session.student_id, problem=self._problem_text(session),
                status=session.status, phase=session.phase, started_at=session.started_at,
                ended_at=session.ended_at, events=len(self._store.list_trace_events(session.id)),
            ))
        return TraceIndex(sessions=rows)

    def trace_export(self, session_ids: list[UUID] | None = None) -> TraceExport:
        wanted = session_ids or self._store.traced_sessions()
        return TraceExport(exported_at=rec.now(), sessions=[self.trace_view(i) for i in wanted])

    def _save_trace(self, session_id: UUID | None, buffer: session_trace.Buffer | None) -> None:
        """Save one call's events through history. A failure here is logged, never raised into the turn."""
        if buffer is None or not buffer.events:
            return
        try:
            if session_id is None or self._store.get_session(session_id) is None:
                # No session to file them under (the start failed): keep them in the log as JSON.
                log.warning("trace (no session): %s", json.dumps(
                    [{"at": p.at.isoformat(), **p.payload.model_dump(mode="json")} for p in buffer.events]))
                return
            self._store.add_trace_events(session_id, [
                rec.TraceEvent(session_id=session_id, at=p.at, payload=p.payload) for p in buffer.events
            ])
        except Exception:
            log.error("trace: could not save the events of session %s", session_id, exc_info=True)

    def _counters(self, session: rec.Session) -> dict:
        drafts = self._store.list_reply_drafts(session.id)
        return {
            "hints_used": session.hints_used,
            "hint_owed": session.last_reply_taught,
            "teach_turns": session.teach_turns,
            "not_yet_count": session.not_yet_count,
            "transfer_attempts": sum(1 for a in self._store.list_attempts(session.id) if a.phase == "stress_test"),
            "drafts": len(drafts),
            "verifier_rejections": sum(1 for d in drafts if d.outcome == "verifier_rejected"),
        }

    def _trace_response(self, session: rec.Session, text: str) -> None:
        practice = session.active_practice_problem
        session_trace.record(
            session_trace.StudentResponse, text=text, blank=not text.strip(), phase=session.phase,
            kind="first_thought" if session.phase == "ask_first_thought"
            else "follow_up_attempt" if session.phase == "stress_test" else "teaching_reply",
            problem_id=session.problem_id, practice_follow_up_id=practice.follow_up_id if practice else None,
            problem=self._teaching_problem(session)[0] if session.phase != "stress_test"
            else self._store.latest_follow_up(session.id).problem_text,  # type: ignore[union-attr]
            tutor_message=session.last_tutor_message if session.phase != "stress_test" else None,
            concept_state=self._concept_state(session), counters=self._counters(session),
        )

    def _trace_transition(self, session: rec.Session, previous: str, trigger: str) -> None:
        practice = session.active_practice_problem
        session_trace.record(
            session_trace.StateTransition, previous_phase=previous, trigger=trigger, new_phase=session.phase,
            status=session.status, practice_follow_up_id=practice.follow_up_id if practice else None,
            counters=self._counters(session),
        )

    def _trace_end(self, session: rec.Session, reason: str) -> None:
        counters = self._counters(session)
        ended = session.ended_at or rec.now()
        session_trace.record(
            session_trace.SessionEnded, reason=reason, status=session.status, phase=session.phase,
            verified=session.status == "verified", transfer_attempts=counters["transfer_attempts"],
            transfer_succeeded=session.status == "verified",
            duration_seconds=round((ended - session.started_at).total_seconds(), 1), counters=counters,
        )

    # ---- helpers ----

    def _follow_up_evidence(self, session: rec.Session) -> dict:
        """The student's own work this session, for a personal follow-up (F14)."""
        prior = self._prior(session)
        decision = self._store.latest_strategy_decision(session.id)
        return {
            "student_answers": [a.text for a in self._store.list_attempts(session.id) if a.phase != "stress_test"],
            "last_steps": prior.steps if prior else [],
            "method": decision.method if decision else None,
        }

    def _cycle_start(self, session: rec.Session):
        """When this teaching cycle began: after the last stress-test answer, if any (else the session start)."""
        judged = [a.created_at for a in self._store.list_attempts(session.id) if a.phase == "stress_test"]
        return judged[-1] if judged else None

    def _cycle_decision(self, session: rec.Session) -> rec.StrategyDecision | None:
        """The last teaching move delivered in this cycle: the one the verdict credits (never an earlier cycle's)."""
        start = self._cycle_start(session)
        decisions = [d for d in self._store.list_strategy_decisions(session.id) if start is None or d.created_at > start]
        return decisions[-1] if decisions else None

    def _earlier_correct_steps(self, session: rec.Session, also_with_wrong: bool = False) -> list[Step]:
        """Correct steps the student already showed in this cycle, from answers with no wrong step (or from every
        answer: the work a correction may build on)."""
        start = self._cycle_start(session)
        found: list[Step] = []
        for attempt in self._store.list_attempts(session.id):
            if attempt.phase == "stress_test" or (start is not None and attempt.created_at <= start):
                continue
            steps = self._store.list_steps(attempt.id)
            if steps and (also_with_wrong or not any(s.status == "wrong" for s in steps)):
                found += [Step(role=s.role, status=s.status, quote=s.quote) for s in steps if s.status == "correct"]
        return found

    def _prior(self, session: rec.Session) -> PriorDiagnosis | None:
        """The last teaching turn's steps and gap, so the tutor's code can check repair."""
        diagnosis = self._store.latest_diagnosis(session.id)
        # On a practice problem only this cycle's work counts: steps of the original problem are another problem's.
        start = self._cycle_start(session) if session.active_practice_problem else None
        for attempt in reversed(self._store.list_attempts(session.id)):
            if start is not None and attempt.created_at <= start:
                break
            steps = self._store.list_steps(attempt.id)
            work = attempt.response_to == "original_problem" or any(s.status == "wrong" for s in steps)
            if attempt.phase != "stress_test" and steps and work:
                return PriorDiagnosis(
                    steps=[Step(role=s.role, status=s.status, quote=s.quote) for s in steps],
                    main_gap=diagnosis.main_gap if diagnosis else None,
                )
        return None

    def _open(self, session_id: UUID) -> rec.Session:
        session = self._store.get_session(session_id)
        if session is None:
            raise ApiError(404, "unknown_session", "No session with that id.")
        if session.status != "active":
            raise ApiError(409, "session_over", "This session has ended.")
        return session

    def _student(self, student_id: UUID) -> rec.Student:
        student = self._store.get_student(student_id)
        if student is None:
            raise ApiError(404, "unknown_student", "No learner with that id.")
        return student

    def _concept(self, session: rec.Session) -> rec.Concept:
        concept = self._store.get_concept(session.concept_id) if session.concept_id else None
        if concept is None:
            raise _internal("Session has no concept.")
        return concept

    def _teaching_problem(self, session: rec.Session) -> tuple[str, Solution]:
        """The problem this teaching cycle works on: the practice problem after a first NOT YET, else the original."""
        practice = session.active_practice_problem
        if practice is not None:
            return practice.text, Solution(**practice.solution.model_dump())
        return self._problem_text(session), self._solution(session)

    async def _practice_problem(self, follow_up: rec.FollowUp) -> rec.PracticeProblem:
        try:
            setup = await self._ask(self._tutor.set_up(follow_up.problem_text, None))
        except Exception as exc:
            log.warning("tutor set_up of the practice problem failed (follow-up %s)", follow_up.id, exc_info=True)
            error = _unavailable()
            session_trace.record_error("practice_set_up", error, cause=exc)
            raise error from exc
        return rec.PracticeProblem(
            follow_up_id=follow_up.id, text=follow_up.problem_text,
            solution=rec.SessionSolution(**setup.solution.model_dump()),
        )

    def _problem_text(self, session: rec.Session) -> str:
        problem = self._store.get_problem(session.problem_id)
        if problem is None:
            raise _internal("Session has no problem.")
        return problem.text

    def _solution(self, session: rec.Session) -> Solution:
        if session.hidden_solution is None:
            raise _internal("Session has no solution.")
        return Solution(**session.hidden_solution.model_dump())

    def _concept_state(self, session: rec.Session) -> State:
        if session.concept_id is None:
            raise _internal("Session has no concept.")
        state = self._store.get_concept_state(session.student_id, session.concept_id)
        return state.state if state else "untested"

    @staticmethod
    def _next_state(before: State, verified: bool, reason: NotYetReason | None = None) -> State:
        if verified:
            return "verified"
        if reason == "hint_limit":
            # The student solved the fresh problem correctly on their own; the NOT YET is about how much help they
            # needed, not evidence that they lost the concept. A verified concept stays verified.
            return "fragile" if before == "untested" else before
        return "fragile" if before in ("verified", "untested") else before

    def _counts(self, student_id: UUID, gap: GapType, method: Strategy) -> EvidenceCounts:
        for stat in self._store.strategy_stats(student_id, gap):
            if stat.method == method:
                return EvidenceCounts(uses=stat.uses, independent_successes=stat.independent_successes)
        return EvidenceCounts(uses=0, independent_successes=0)

    @staticmethod
    def _turn(
        session: rec.Session, message: str, check: ReplyCheckView, follow_up: FollowUpView | None = None
    ) -> TutorTurn:
        return TutorTurn(
            session_id=session.id,
            phase="teach" if session.phase == "verdict" else session.phase,  # a teaching turn, never a verdict
            message=message,
            follow_up=follow_up,
            hints_used=session.hints_used,
            reply_check=check,
        )

    def _blank_turn(self, session: rec.Session) -> TutorTurn:
        """Blank text: one short question, no help. In the stress test the same problem is shown again."""
        check = ReplyCheckView(approved=True, summary="Asked one short question.", outcome="fixed_reply")
        session_trace.record(
            session_trace.ReplySent, kind="blank_prompt",
            message=EMPTY_STRESS_TEST if session.phase == "stress_test" else EMPTY_PROBE, reply_outcome="fixed_reply",
            method=None, shown_to_student=True, counts_as_hint=False,
        )
        if session.phase != "stress_test":
            # Not a teaching move: nothing is saved, so a hint owed for an earlier move stays owed and the outstanding
            # tutor message stays as context.
            return self._turn(session, EMPTY_PROBE, check)
        saved = self._store.latest_follow_up(session.id)
        if saved is None:
            raise _internal("Session is in the stress test without a follow-up.")
        return self._turn(session, EMPTY_STRESS_TEST, check, FollowUpView(problem=saved.problem_text))
