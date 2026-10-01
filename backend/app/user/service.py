import hashlib
import re
from uuid import UUID

from app.common.vocab import GapType, State, Strategy
from app.history import HistoryStore
from app.history import schema as rec
from app.tutor.schema import EvidenceCounts, FollowUpDraft
from app.user.errors import ApiError
from app.user.ports import (
    FollowUpRequest,
    FollowUpResult,
    JudgeRequest,
    TeachRequest,
    TutorPort,
)
from app.user.schema import (
    AttemptResponse,
    ConceptChange,
    DiagnosisView,
    ExitResponse,
    FollowUpView,
    LearnerConcept,
    LearnerView,
    MethodTotal,
    MethodView,
    ReplyCheckView,
    SessionStartRequest,
    SessionStartResponse,
    Solution,
    StrategyChange,
    StrategyRow,
    StrategyView,
    TutorTurn,
    Verdict,
    VerdictChanges,
    VerdictTurn,
)

MAX_TEACH_TURNS = 4  # move to the stress test after this many teaching turns regardless
MAX_NOT_YET = 2  # the second NOT YET ends the session
MAX_HINTS_FOR_VERIFIED = 2  # a correct answer after more hints than this is a lucky one (F16)
MAX_FOLLOW_UP_TRIES = 3  # a repeated follow-up is regenerated this many times, then we give up

FIRST_THOUGHT_PROMPT = "Before I help, what would you try first? Even an incomplete idea is useful."
EMPTY_PROBE = "What is one thing you notice in the problem?"
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

    def __init__(self, tutor: TutorPort, store: HistoryStore) -> None:
        self._tutor = tutor
        self._store = store

    # ---- start and exit ----

    async def start(self, req: SessionStartRequest) -> SessionStartResponse:
        if self._store.get_student(req.student_id) is None:
            raise ApiError(404, "unknown_student", "No learner with that id.")
        try:
            setup = await self._tutor.set_up(req.problem, req.subject)
        except Exception as exc:  # a bad agent reply must never become a 500 (F25)
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

    def exit(self, session_id: UUID) -> ExitResponse:
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

    # ---- the turn endpoint ----

    async def attempt(self, session_id: UUID, text: str) -> AttemptResponse:
        session = self._open(session_id)
        if not text.strip():
            # Never explain instead of asking; nothing is saved and the agent is not called
            return self._turn(session, EMPTY_PROBE, ReplyCheckView(approved=True, summary="Asked one short question."))
        if session.phase == "stress_test":
            return await self._judge(session, text)
        return await self._teach(session, text)

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
        )
        try:
            result = await self._tutor.teach(request)
        except Exception:
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
        # The app records the tool's result; what history credits never comes from the model's wording
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

        if out.gap_repaired or turns >= MAX_TEACH_TURNS:
            return await self._stress_test(session, out.main_gap)
        return TutorTurn(
            session_id=session.id,
            phase="teach",
            message=out.reply,
            diagnosis=DiagnosisView(
                steps=out.steps, main_gap=out.main_gap, alternatives=out.alternatives, confidence=out.confidence
            ),
            method=MethodView(
                name=method.method, mode=method.mode, experiment=method.mode == "experiment", reason=method.reason
            ),
            hints_used=session.hints_used,
            reply_check=result.reply_check,
        )

    async def _stress_test(self, session: rec.Session, main_gap: GapType) -> TutorTurn:
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
        return TutorTurn(
            session_id=session.id,
            phase="stress_test",
            message=result.message,
            follow_up=FollowUpView(problem=draft.problem),  # the rubric stays on the backend
            hints_used=session.hints_used,
            reply_check=result.reply_check,
        )

    async def _new_follow_up(self, session: rec.Session, main_gap: GapType) -> tuple[FollowUpResult, str]:
        """Ask for a follow-up and regenerate while it repeats something this student has seen."""
        seen = {s.fingerprint for s in self._store.seen_fingerprints(session.student_id)}
        retry_reason: str | None = None
        for _ in range(MAX_FOLLOW_UP_TRIES):
            try:
                result = await self._tutor.follow_up(
                    FollowUpRequest(
                        student_id=session.student_id,
                        problem=self._problem_text(session),
                        concept_name=self._concept(session).name,
                        solution=self._solution(session),
                        main_gap=main_gap,
                        hints_used=session.hints_used,
                        retry_reason=retry_reason,
                    )
                )
            except Exception as exc:
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
        if follow_up is None or diagnosis is None or decision is None:
            raise _internal("Session is missing its follow-up, diagnosis or method.")
        concept = self._concept(session)
        try:
            check = await self._tutor.judge(
                JudgeRequest(
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
            )
        except Exception as exc:
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
        gap, method = diagnosis.main_gap, decision.method
        before_state = self._concept_state(session)
        after_state = self._next_state(before_state, verified)
        before_counts = self._counts(session.student_id, gap, method)
        over = verified or session.not_yet_count + 1 >= MAX_NOT_YET

        self._store.record_verdict(
            rec.Outcome(
                student_id=session.student_id,
                session_id=session.id,
                concept_id=concept.id,
                gap_type=gap,
                method=method,
                decision_mode=decision.decision_mode,
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
                    strategy=StrategyChange(
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
    def _turn(session: rec.Session, message: str, check: ReplyCheckView) -> TutorTurn:
        return TutorTurn(
            session_id=session.id,
            phase="teach" if session.phase == "verdict" else session.phase,  # a teaching turn, never a verdict
            message=message,
            hints_used=session.hints_used,
            reply_check=check,
        )
