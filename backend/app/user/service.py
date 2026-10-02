import asyncio
import contextvars
import hashlib
import logging
import re
from collections.abc import Awaitable
from uuid import UUID

from app.common.vocab import GapType, State, Strategy
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
from app.user.schema import LearnerConcept, LearnerView, MethodTotal, StrategyRow, StrategyView

log = logging.getLogger(__name__)

MAX_TEACH_TURNS = 4  # move to the stress test after this many teaching turns regardless
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

    def __init__(self, tutor: TutorPort, store: HistoryStore, timeout: float | None = None) -> None:
        """`timeout` replaces both budgets (the tests use a short one)."""
        self._tutor = tutor
        self._store = store
        self._start_budget = START_BUDGET_SECONDS if timeout is None else timeout
        self._turn_budget = TURN_BUDGET_SECONDS if timeout is None else timeout
        self._deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar("deadline", default=None)
        # Sessions whose gap is repaired but whose follow-up could not be made yet, with the gap to build it from
        self._follow_up_owed: dict[UUID, GapType | None] = {}
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
        if self._store.get_student(req.student_id) is None:
            raise ApiError(404, "unknown_student", "No learner with that id.")
        self._begin_budget(self._start_budget)
        try:
            setup = await self._ask(self._tutor.set_up(req.problem, req.subject))
        except Exception as exc:  # a bad agent reply must never become a 500 (F25)
            log.warning("tutor set_up failed", exc_info=True)
            raise _unavailable() from exc
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
        return SessionStartResponse(
            session_id=session.id, phase=session.phase, message=FIRST_THOUGHT_PROMPT, hints_used=0
        )

    async def exit(self, session_id: UUID) -> ExitResponse:
        try:
            async with self._lock(session_id):  # wait for a turn that is still running
                session = self._open(session_id)
                if session.hidden_solution is None:
                    raise _internal("Session has no solution.")
                session.phase = "exited"
                session.status = "exited"
                session.ended_at = rec.now()
                self._store.update_session(session)  # no outcome is written: exit records no evidence
                return ExitResponse(
                    phase="exited",
                    solution=Solution(**session.hidden_solution.model_dump()),
                    evidence_recorded=False,
                )
        finally:
            self._forget_lock(session_id)

    # ---- the turn endpoint ----

    async def attempt(self, session_id: UUID, text: str) -> AttemptResponse:
        try:
            async with self._lock(session_id):  # the state is read inside the lock, after any turn ahead of us
                session = self._open(session_id)
                self._begin_budget(self._turn_budget)
                if session_id in self._follow_up_owed:
                    # The gap was repaired but the follow-up failed last time. Do not teach again (that would
                    # cost another hint for the model's failure): just make the follow-up.
                    return await self._stress_test(session, self._follow_up_owed[session_id])
                if not text.strip():
                    # Never explain instead of asking; nothing is saved and the agent is not called
                    return self._blank_turn(session)
                if session.phase == "stress_test":
                    return await self._judge(session, text)
                return await self._teach(session, text)
        finally:
            self._forget_lock(session_id)

    async def _teach(self, session: rec.Session, text: str) -> TutorTurn:
        concept = self._concept(session)
        first = session.phase == "ask_first_thought"
        hints = session.hints_used + (0 if first else 1)  # the student needed the previous move
        turns = session.teach_turns + 1
        request = TeachRequest(
            student_id=session.student_id,
            problem=self._problem_text(session),
            concept_name=concept.name,
            solution=self._solution(session),
            student_text=text,
            first_thought=first,
            hints_used=hints,
            teach_turns=turns,
            force_experiment=session.force_experiment,
            after_not_yet=session.not_yet_count > 0 and session.teach_turns == 0,
            prior=self._prior(session),
        )
        try:
            result = await self._ask(self._tutor.teach(request))
        except Exception:
            log.warning("tutor teach failed; sent the safe fallback (session %s)", session.id, exc_info=True)
            return self._turn(session, SAFE_FALLBACK, ReplyCheckView(approved=False, summary="Safe fallback used."))

        out, method = result.output, result.method
        attempt = rec.Attempt(session_id=session.id, phase=session.phase, text=text)
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
        # The app records the tool's result; what history credits never comes from the model's wording.
        # A probe or an acknowledgement uses no method, so nothing is recorded for it.
        if method is not None and out.main_gap is not None:
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
        self._store.update_session(session)

        # Move on when the gap is repaired, when every step already holds (the skip rule;
        # being right is still not VERIFIED), or after the turn cap.
        no_gap = out.main_gap is None and out.evidence == "sufficient"
        if out.gap_repaired or no_gap or turns >= MAX_TEACH_TURNS:
            self._follow_up_owed[session.id] = out.main_gap  # cleared once the follow-up exists
            return await self._stress_test(session, out.main_gap)
        return TutorTurn(
            session_id=session.id,
            phase="teach",
            message=out.reply,
            diagnosis=DiagnosisView(
                steps=out.steps, main_gap=out.main_gap, alternatives=out.alternatives, confidence=out.confidence
            ),
            method=None
            if method is None
            else MethodView(
                name=method.method, mode=method.mode, experiment=method.mode == "experiment", reason=method.reason
            ),
            hints_used=session.hints_used,
            reply_check=result.reply_check,
        )

    async def _stress_test(self, session: rec.Session, main_gap: GapType | None) -> TutorTurn:
        result, new_fingerprint = await self._new_follow_up(session, main_gap)
        draft = result.output.follow_up
        self._store.add_follow_up(
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
        self._store.update_session(session)
        self._follow_up_owed.pop(session.id, None)
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
        for _ in range(MAX_FOLLOW_UP_TRIES):
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
                result = await self._ask(self._tutor.follow_up(request))
            except Exception as exc:
                log.warning("tutor follow_up failed (session %s)", session.id, exc_info=True)
                raise _unavailable() from exc
            new_fingerprint = fingerprint(result.output.follow_up.problem)
            if new_fingerprint not in seen:
                return result, new_fingerprint
            retry_reason = "The student has already seen this problem."
        raise _unavailable()

    async def _judge(self, session: rec.Session, text: str) -> VerdictTurn:
        follow_up = self._store.latest_follow_up(session.id)
        diagnosis = self._store.latest_diagnosis(session.id)
        decision = self._store.latest_strategy_decision(session.id)
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
            raise _unavailable() from exc

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

        # Code decides VERIFIED: the verifier's judgement, the hint count, and a fresh problem
        independent = check.own_work and session.hints_used <= MAX_HINTS_FOR_VERIFIED
        verified = check.correct and independent
        # Credit goes to the method that was recorded; a session that taught nothing credits none.
        gap = decision.gap_type if decision else None
        method = decision.method if decision else None
        before_state = self._concept_state(session)
        after_state = self._next_state(before_state, verified)
        before_counts = self._counts(session.student_id, gap, method) if gap and method else None
        over = verified or session.not_yet_count + 1 >= MAX_NOT_YET

        self._store.record_verdict(
            rec.Outcome(
                student_id=session.student_id,
                session_id=session.id,
                concept_id=concept.id,
                gap_type=gap,
                method=method,
                decision_mode=decision.decision_mode if decision else None,
                result="VERIFIED" if verified else "NOT YET",
                independent=independent,
                hints_used=session.hints_used,
                concept_before=before_state,
                concept_after=after_state,
                evidence=check.note,
                remaining_gap=None if verified else gap,
            ),
            session_over=over,
        )
        # record_verdict moved the session to the verdict phase; after a first NOT YET it goes back to teaching
        session = self._store.get_session(session.id) or session
        if not verified:
            session.not_yet_count += 1
        if not over:
            session.phase = "teach"
            session.teach_turns = 0
        self._store.update_session(session)

        if verified:
            message = "You solved it on your own."
        elif over:
            message = f"Not yet, and that is okay. What we learned: {check.note} You can exit when you like."
        else:
            message = "Not yet. Here is what we will try differently."
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
                        gap=gap, method=method, before=before_counts, after=self._counts(session.student_id, gap, method)
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

    def _prior(self, session: rec.Session) -> PriorDiagnosis | None:
        """The last teaching turn's steps and gap, so the tutor's code can check repair."""
        diagnosis = self._store.latest_diagnosis(session.id)
        for attempt in reversed(self._store.list_attempts(session.id)):
            steps = self._store.list_steps(attempt.id)
            if attempt.phase != "stress_test" and steps:
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
    def _next_state(before: State, verified: bool) -> State:
        if verified:
            return "verified"
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
        check = ReplyCheckView(approved=True, summary="Asked one short question.")
        if session.phase != "stress_test":
            return self._turn(session, EMPTY_PROBE, check)
        saved = self._store.latest_follow_up(session.id)
        if saved is None:
            raise _internal("Session is in the stress test without a follow-up.")
        return self._turn(session, EMPTY_STRESS_TEST, check, FollowUpView(problem=saved.problem_text))
