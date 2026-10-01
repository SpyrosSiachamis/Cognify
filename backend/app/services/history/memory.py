"""In-memory HistoryStore: one plain list per record kind.

The backend must run a SINGLE worker with this store (one process, one set of
lists). Every write, and all of record_verdict, holds one lock. Reads and
writes hand out copies, never the stored objects.
"""

import threading
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from app.common.vocab import GapType

from .schema import (
    Attempt,
    AttemptStep,
    Concept,
    ConceptState,
    Diagnosis,
    FollowUp,
    Outcome,
    Problem,
    SeenFingerprint,
    Session,
    Student,
    StrategyDecision,
    StrategyStat,
    VerifierCheck,
)

M = TypeVar("M", bound=BaseModel)


def _copy(record: M) -> M:
    return record.model_copy(deep=True)


class InMemoryHistory:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._students: list[Student] = []
        self._concepts: list[Concept] = []
        self._problems: list[Problem] = []
        self._sessions: list[Session] = []
        self._attempts: list[Attempt] = []
        self._steps: list[AttemptStep] = []
        self._diagnoses: list[Diagnosis] = []
        self._decisions: list[StrategyDecision] = []
        self._follow_ups: list[FollowUp] = []
        self._checks: list[VerifierCheck] = []
        self._outcomes: list[Outcome] = []
        self._states: list[ConceptState] = []
        self._seed_states: list[ConceptState] = []  # what reset_demo restores

    # ---- helpers (no locking: callers already hold the lock) ----

    def _find_session(self, session_id: UUID) -> Session:
        for session in self._sessions:
            if session.id == session_id:
                return session
        raise KeyError(f"unknown session {session_id}")

    def _find_state(self, student_id: UUID, concept_id: UUID) -> ConceptState | None:
        for state in self._states:
            if state.student_id == student_id and state.concept_id == concept_id:
                return state
        return None

    def _upsert_state(self, state: ConceptState) -> ConceptState:
        stored = _copy(state)
        self._states = [
            s
            for s in self._states
            if (s.student_id, s.concept_id) != (state.student_id, state.concept_id)
        ]
        self._states.append(stored)
        return stored

    # ---- students and concepts ----

    def get_student(self, student_id: UUID) -> Student | None:
        with self._lock:
            return next((_copy(s) for s in self._students if s.id == student_id), None)

    def list_students(self) -> list[Student]:
        with self._lock:
            return [_copy(s) for s in self._students]

    def get_or_create_concept(self, name: str) -> Concept:
        key = name.strip().lower()
        with self._lock:
            for concept in self._concepts:
                if concept.name.strip().lower() == key:
                    return _copy(concept)
            concept = Concept(name=name.strip())
            self._concepts.append(concept)
            return _copy(concept)

    # ---- problems and sessions ----

    def add_problem(self, problem: Problem) -> Problem:
        with self._lock:
            self._problems.append(_copy(problem))
            return _copy(problem)

    def create_session(self, session: Session) -> Session:
        with self._lock:
            if not any(s.id == session.student_id for s in self._students):
                raise KeyError(f"unknown student {session.student_id}")
            if not any(p.id == session.problem_id for p in self._problems):
                raise KeyError(f"unknown problem {session.problem_id}")
            self._sessions.append(_copy(session))
            return _copy(session)

    def get_session(self, session_id: UUID) -> Session | None:
        with self._lock:
            return next((_copy(s) for s in self._sessions if s.id == session_id), None)

    def update_session(self, session: Session) -> Session:
        with self._lock:
            self._find_session(session.id)
            self._sessions = [_copy(session) if s.id == session.id else s for s in self._sessions]
            return _copy(session)

    # ---- attempts with their steps ----

    def add_attempt(self, attempt: Attempt, steps: list[AttemptStep]) -> Attempt:
        with self._lock:
            self._find_session(attempt.session_id)
            if any(step.attempt_id != attempt.id for step in steps):
                raise ValueError("every step must belong to this attempt")
            self._attempts.append(_copy(attempt))
            self._steps.extend(_copy(step) for step in steps)
            return _copy(attempt)

    def list_attempts(self, session_id: UUID) -> list[Attempt]:
        with self._lock:
            return [_copy(a) for a in self._attempts if a.session_id == session_id]

    def list_steps(self, attempt_id: UUID) -> list[AttemptStep]:
        with self._lock:
            steps = [s for s in self._steps if s.attempt_id == attempt_id]
            return [_copy(s) for s in sorted(steps, key=lambda s: s.position)]

    # ---- saved during the session ----

    def add_diagnosis(self, diagnosis: Diagnosis) -> Diagnosis:
        with self._lock:
            if not any(a.id == diagnosis.attempt_id for a in self._attempts):
                raise KeyError(f"unknown attempt {diagnosis.attempt_id}")
            self._diagnoses.append(_copy(diagnosis))
            return _copy(diagnosis)

    def add_strategy_decision(self, decision: StrategyDecision) -> StrategyDecision:
        with self._lock:
            self._find_session(decision.session_id)
            self._decisions.append(_copy(decision))
            return _copy(decision)

    def add_follow_up(self, follow_up: FollowUp) -> FollowUp:
        with self._lock:
            self._find_session(follow_up.session_id)
            self._follow_ups.append(_copy(follow_up))
            return _copy(follow_up)

    def add_verifier_check(self, check: VerifierCheck) -> VerifierCheck:
        with self._lock:
            self._find_session(check.session_id)
            self._checks.append(_copy(check))
            return _copy(check)

    # ---- concept state ----

    def get_concept_state(self, student_id: UUID, concept_id: UUID) -> ConceptState | None:
        with self._lock:
            state = self._find_state(student_id, concept_id)
            return _copy(state) if state else None

    def upsert_concept_state(self, state: ConceptState) -> ConceptState:
        with self._lock:
            return _copy(self._upsert_state(state))

    def list_concept_states(self, student_id: UUID) -> list[ConceptState]:
        with self._lock:
            return [_copy(s) for s in self._states if s.student_id == student_id]

    # ---- derived reads (same meaning as the Postgres views we will write) ----

    def strategy_stats(
        self, student_id: UUID, gap_type: GapType | None = None
    ) -> list[StrategyStat]:
        with self._lock:
            groups: dict[tuple[str, str], list[Outcome]] = {}
            for o in self._outcomes:
                if o.student_id == student_id and gap_type in (None, o.gap_type):
                    groups.setdefault((o.gap_type, o.method), []).append(o)
            stats = []
            for (gap, method), rows in sorted(groups.items()):
                successes = [o for o in rows if o.result == "VERIFIED" and o.independent]
                stats.append(
                    StrategyStat(
                        student_id=student_id,
                        gap_type=gap,
                        method=method,
                        uses=len(rows),
                        independent_successes=len(successes),
                        experiments=sum(o.decision_mode == "experiment" for o in rows),
                        last_used_at=max(o.created_at for o in rows),
                        last_success_at=max((o.created_at for o in successes), default=None),
                    )
                )
            return stats

    def seen_fingerprints(self, student_id: UUID) -> list[SeenFingerprint]:
        with self._lock:
            session_ids = {s.id for s in self._sessions if s.student_id == student_id}
            problem_ids = {s.problem_id for s in self._sessions if s.id in session_ids}
            found = [("problem", p.fingerprint) for p in self._problems if p.id in problem_ids]
            found += [
                ("follow_up", f.fingerprint)
                for f in self._follow_ups
                if f.session_id in session_ids
            ]
            return [
                SeenFingerprint(student_id=student_id, fingerprint=fingerprint, kind=kind)
                for kind, fingerprint in dict.fromkeys(found)
            ]

    # ---- verdict and demo ----

    def record_verdict(self, outcome: Outcome, session_over: bool = True) -> ConceptState:
        """Write the outcome, the concept state and the session together, or nothing."""
        with self._lock:
            # Check everything first, so a failure leaves nothing half-written.
            if not any(s.id == outcome.student_id for s in self._students):
                raise KeyError(f"unknown student {outcome.student_id}")
            if not any(c.id == outcome.concept_id for c in self._concepts):
                raise KeyError(f"unknown concept {outcome.concept_id}")
            session = None
            if outcome.session_id is not None:
                session = self._find_session(outcome.session_id)
                if session.student_id != outcome.student_id:
                    raise ValueError("the session belongs to a different student")
            current = self._find_state(outcome.student_id, outcome.concept_id)
            current_state = current.state if current else "untested"
            if outcome.concept_before != current_state:
                raise ValueError(
                    f"concept_before is {outcome.concept_before} but the stored state is "
                    f"{current_state}"
                )

            # Now write.
            self._outcomes.append(_copy(outcome))
            new_state = self._upsert_state(
                ConceptState(
                    student_id=outcome.student_id,
                    concept_id=outcome.concept_id,
                    state=outcome.concept_after,
                    evidence=(current.evidence if current else []) + [outcome.evidence],
                    is_seeded=False,
                    updated_at=outcome.created_at,
                )
            )
            if session is not None:
                session.phase = "verdict"
                if session_over:
                    session.ended_at = outcome.created_at
            return _copy(new_state)

    def load_seed(
        self,
        students: list[Student],
        concepts: list[Concept],
        outcomes: list[Outcome],
        concept_states: list[ConceptState],
    ) -> None:
        """Insert seeded rows. Safe to call twice: rows already present are skipped."""
        everything = [*students, *concepts, *outcomes, *concept_states]
        if not all(getattr(row, "is_seeded", True) for row in everything):
            raise ValueError("load_seed only accepts rows with is_seeded=True")
        with self._lock:
            for table, rows in (
                (self._students, students),
                (self._concepts, concepts),
                (self._outcomes, outcomes),
            ):
                known = {row.id for row in table}
                table.extend(_copy(row) for row in rows if row.id not in known)
            for state in concept_states:
                if self._find_state(state.student_id, state.concept_id) is None:
                    self._upsert_state(state)
            self._seed_states = [_copy(s) for s in concept_states]

    def reset_demo(self) -> None:
        """Back to the seeded Maria and Nikos. Seeded outcomes are never deleted."""
        with self._lock:
            demo_ids = {s.id for s in self._students if s.is_seeded}
            session_ids = {s.id for s in self._sessions if s.student_id in demo_ids}
            attempt_ids = {a.id for a in self._attempts if a.session_id in session_ids}
            problem_ids = {s.problem_id for s in self._sessions if s.id in session_ids}

            self._sessions = [s for s in self._sessions if s.id not in session_ids]
            self._attempts = [a for a in self._attempts if a.id not in attempt_ids]
            self._steps = [s for s in self._steps if s.attempt_id not in attempt_ids]
            self._diagnoses = [d for d in self._diagnoses if d.attempt_id not in attempt_ids]
            self._decisions = [d for d in self._decisions if d.session_id not in session_ids]
            self._follow_ups = [f for f in self._follow_ups if f.session_id not in session_ids]
            self._checks = [c for c in self._checks if c.session_id not in session_ids]
            self._problems = [p for p in self._problems if p.id not in problem_ids]
            self._outcomes = [
                o for o in self._outcomes if o.is_seeded or o.student_id not in demo_ids
            ]
            self._states = [s for s in self._states if s.student_id not in demo_ids]
            for state in self._seed_states:
                if state.student_id in demo_ids:
                    self._upsert_state(state)
