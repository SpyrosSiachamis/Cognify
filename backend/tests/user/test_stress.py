"""Randomised stress test of the session flow (F25, F29).

Seeded random sequences of starts, attempts (blank, huge, Greek, bursts of simultaneous ones),
exits and views run against a tutor that randomly fails, is slow, probes, finds no gap, repairs
early or judges wrongly. After every step, invariants that must always hold are checked against
what the history store actually saved, so a broken lock or a lost write shows up as a failure.
"""

import asyncio
import json
import random
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.history import InMemoryHistory
from app.main import app
from app.seed import seed_store
from app.seed.data import MARIA_ID, NIKOS_ID
from app.session.schema import SessionStartRequest, VerdictTurn
from app.tutor.schema import Step, TutorTeachingOutput, TutorTurn
from app.user.errors import ApiError
from app.user.ports import TeachResult
from app.user.router import get_service
from app.user.service import MAX_HINTS_FOR_VERIFIED, MAX_NOT_YET, SessionService
from app.user.stub_tutor import StubTutor
from tests.user.conftest import BALL

SEEDS = range(30)
STEPS = 60
TEXTS = ["", "   ", "\n\t", "idea", "I found the time, 2.04 s", "x" * 4000, "Βρήκα τον χρόνο", "🙂 ok", "v^2 = u^2 - 2gh", "a"]
SECRETS = ("hidden", "rubric", "400 / 19.6", "At the highest point v = 0")  # hidden fields and solution text; only exit shows the solution


class ChaosTutor(StubTutor):
    """The stub, with every behaviour the real agent might show decided by a seeded random generator."""

    def __init__(self, rng: random.Random) -> None:
        super().__init__()
        self.rng = rng

    def _roll(self, p: float) -> bool:
        return self.rng.random() < p

    async def _arrive(self, name: str) -> None:
        await asyncio.sleep(0)  # let simultaneous requests interleave
        if self._roll(0.03):
            await asyncio.sleep(0.2)  # slower than the service's time limit
        if self._roll(0.08):
            raise RuntimeError(f"{name} failed")

    async def set_up(self, problem, subject):
        await self._arrive("set_up")
        return await super().set_up(problem, subject)

    async def teach(self, request):
        await self._arrive("teach")
        result = await super().teach(request)
        kind = self.rng.choice(["gap", "gap", "probe", "no_gap"])
        if kind == "gap":
            result.output.gap_repaired = self._roll(0.3)
            # A repair here finishes the stub's whole problem, so that is when support may go.
            result.output.resolution = "PROBLEM_RESOLVED" if result.output.gap_repaired else "CURRENT_TARGET_UNRESOLVED"
        elif kind == "probe":  # not enough evidence yet: a question, no method, no gap
            output = TutorTeachingOutput(
                steps=[Step(role="choose_method", status="missing")], main_gap=None, confidence="low",
                evidence="insufficient", gap_repaired=False, reply="What did you try first?",
            )
            return TeachResult(output=output, method=None, reply_check=result.reply_check)
        else:  # every step holds: straight to the stress test, nothing was taught
            output = TutorTeachingOutput(
                steps=[Step(role="choose_method", status="correct", quote="v^2 = u^2 - 2gh")], main_gap=None,
                confidence="high", evidence="sufficient", gap_repaired=False, reply="Every step holds.",
                resolution="PROBLEM_RESOLVED",
            )
            return TeachResult(output=output, method=None, reply_check=result.reply_check)
        return result

    async def judge(self, request):
        await self._arrive("judge")
        check = await super().judge(request)
        check.correct = not self._roll(0.35)
        check.own_work = not self._roll(0.1)
        return check


def pool(store: InMemoryHistory) -> dict:
    """Strategy counts per student, gap and method, from the store."""
    return {
        (stat.student_id, stat.gap_type, stat.method): (stat.uses, stat.independent_successes)
        for student in (MARIA_ID, NIKOS_ID)
        for stat in store.strategy_stats(student)
    }


def assert_no_secrets(payload: dict) -> None:
    text = json.dumps(payload)
    for secret in SECRETS:
        assert secret not in text, f"{secret!r} leaked: {text[:200]}"


def check_session(store: InMemoryHistory, service: SessionService, session_id: UUID) -> None:
    """What must be true of a session at any moment, judged from the saved records."""
    session = store.get_session(session_id)
    assert session is not None
    attempts = store.list_attempts(session_id)
    phases = [a.phase for a in attempts]
    assert phases.count("ask_first_thought") <= 1, "two first thoughts: a turn ran from stale state"
    # A hint is a delivered teaching move (recorded as a decision) that the student then answered (F16).
    delivered = len(store.list_strategy_decisions(session_id))
    assert session.hints_used + int(session.last_reply_taught) == delivered, "hints_used does not match the moves delivered"
    verified = 1 if session.status == "verified" else 0
    assert phases.count("stress_test") == session.not_yet_count + verified, "a stress-test attempt had no verdict"
    assert session.not_yet_count <= MAX_NOT_YET
    if session.status != "active":
        assert session.ended_at is not None
        assert session_id not in service._locks, "an ended session kept its lock"


def check_response(response, state: dict) -> None:
    payload = response.model_dump(mode="json")
    assert_no_secrets(payload)
    sid = payload["session_id"]
    if "hints_used" in payload:  # a verdict turn does not carry the count
        assert payload["hints_used"] >= state.get(sid, 0), "hints_used went down"
        state[sid] = payload["hints_used"]
    if isinstance(response, VerdictTurn):
        verdict = response.verdict
        if verdict.result == "VERIFIED":
            assert verdict.independent and payload["session_over"] is True
            assert state[sid] <= MAX_HINTS_FOR_VERIFIED, "VERIFIED after too many hints"
    else:
        assert isinstance(response, TutorTurn) and response.phase in ("ask_first_thought", "teach", "stress_test")


async def one_run(seed: int) -> None:
    rng = random.Random(seed)
    store = InMemoryHistory()
    seed_store(store)
    service = SessionService(ChaosTutor(rng), store, timeout=0.05)
    sessions: list[UUID] = []
    hints: dict = {}
    counts = pool(store)

    async def attempt(session_id: UUID, text: str):
        try:
            response = await service.attempt(session_id, text)
        except ApiError as exc:
            assert exc.status in (404, 409, 503), f"unexpected {exc.status} {exc.body.code}"
            return None
        check_response(response, hints)
        return response

    for _ in range(STEPS):
        action = rng.choices(["start", "attempt", "burst", "exit", "ghost", "views"], [2, 8, 3, 1, 1, 1])[0]
        if action == "start" or not sessions:
            student = rng.choice([MARIA_ID, NIKOS_ID])
            try:
                started = await service.start(
                    SessionStartRequest(problem=BALL, student_id=student, force_experiment=rng.random() < 0.2)
                )
                sessions.append(started.session_id)
            except ApiError as exc:
                assert exc.status == 503
        elif action == "attempt":
            await attempt(rng.choice(sessions), rng.choice(TEXTS))
        elif action == "burst":  # a double click, or three
            target = rng.choice(sessions)
            await asyncio.gather(*(attempt(target, rng.choice(TEXTS)) for _ in range(rng.randint(2, 3))))
        elif action == "exit":
            target = rng.choice(sessions)
            try:
                result = await service.exit(target)
                assert result.evidence_recorded is False
            except ApiError as exc:
                assert exc.status in (404, 409)
        elif action == "ghost":  # an id that was never a session must not grow any state
            with pytest.raises(ApiError) as caught:
                await service.attempt(uuid4(), "hello")
            assert caught.value.status == 404
        else:
            for student in (MARIA_ID, NIKOS_ID):
                service.learner_view(student)
                strategies = service.strategy_view(student)
                assert all(r.independent_successes <= r.uses for r in strategies.rows)

        for session_id in sessions:
            check_session(store, service, session_id)
        now = pool(store)
        for key, (uses, wins) in counts.items():
            assert now[key][0] >= uses and now[key][1] >= wins, f"strategy count went down for {key}"
        counts = now

    stale = []
    for locked in service._locks:  # a lock for a missing or ended session is a leak
        session = store.get_session(locked)
        if session is None or session.status != "active":
            stale.append(locked)
    assert stale == [], "locks left behind for ended or unknown sessions"


@pytest.mark.parametrize("seed", SEEDS)
def test_random_sessions_keep_every_invariant(seed):
    asyncio.run(one_run(seed))


def test_exit_never_writes_evidence_even_mid_story():
    async def run():
        rng = random.Random(7)
        store = InMemoryHistory()
        seed_store(store)
        service = SessionService(ChaosTutor(rng), store, timeout=0.05)
        before = pool(store)
        for _ in range(20):
            started = None
            while started is None:
                try:
                    started = await service.start(SessionStartRequest(problem=BALL, student_id=MARIA_ID))
                except ApiError:
                    pass
            for _ in range(rng.randint(0, 2)):
                try:
                    await service.attempt(started.session_id, "my idea")
                except ApiError:
                    pass
            await service.exit(started.session_id)
        assert pool(store) == before

    asyncio.run(run())


@pytest.mark.parametrize("seed", range(5))
def test_http_never_answers_500_and_never_leaks(seed):
    """The same randomness through the real routes: only contract statuses, no hidden fields."""
    rng = random.Random(seed)
    store = InMemoryHistory()
    seed_store(store)
    service = SessionService(StubTutor(), store)
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        sessions = []
        for _ in range(80):
            action = rng.choice(["start", "attempt", "attempt", "exit", "junk"])
            if action == "start" or not sessions:
                r = client.post("/api/session", json={"problem": BALL, "student_id": str(rng.choice([MARIA_ID, NIKOS_ID]))})
                if r.status_code == 200:
                    sessions.append(r.json()["session_id"])
            elif action == "attempt":
                r = client.post(f"/api/session/{rng.choice(sessions)}/attempt", json={"text": rng.choice(TEXTS)})
            elif action == "exit":
                r = client.post(f"/api/session/{rng.choice(sessions)}/exit")
                if r.status_code == 200:
                    assert r.json()["evidence_recorded"] is False
                    continue
            else:
                r = client.post(f"/api/session/{rng.choice(sessions)}/attempt", content=rng.choice(["{", "[]", "null", '{"text": 5}']),
                                headers={"content-type": "application/json"})
            assert r.status_code in (200, 404, 409, 422), r.text
            if r.status_code != 200:
                assert set(r.json()) == {"error"} and set(r.json()["error"]) == {"code", "message", "retryable"}
            else:
                assert_no_secrets(r.json())
    finally:
        app.dependency_overrides.clear()
