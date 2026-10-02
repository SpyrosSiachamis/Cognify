"""A client wired to a fresh seeded store and a scriptable stub tutor."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.history import InMemoryHistory
from app.main import app
from app.seed import seed_store
from app.user.router import get_service
from app.user.service import SessionService
from app.user.stub_tutor import StubTutor

BALL = (
    "A ball is thrown vertically upward with an initial velocity of 20 m/s. "
    "How high does it go before it starts to fall? (Use g = 9.8 m/s^2)"
)


class ScriptedTutor(StubTutor):
    """The stub, with repair and judgement controllable, failures injectable and calls recorded."""

    def __init__(self, repair_after=2, correct=True, follow_up_texts=None, fail=(), fail_once=()):
        super().__init__()
        self.repair_after = repair_after
        self.correct = correct
        self.follow_up_texts = list(follow_up_texts or [])
        self.fail = set(fail)
        self.fail_once = set(fail_once)  # fail the first call only, then work
        self.delay = 0.0  # seconds every agent call takes, to make requests overlap
        self.calls = 0
        self.teach_requests = []
        self.follow_up_requests = []

    def _enter(self, name):
        self.calls += 1
        if name in self.fail:
            raise RuntimeError(f"{name} failed")
        if name in self.fail_once:
            self.fail_once.discard(name)
            raise RuntimeError(f"{name} failed once")

    async def set_up(self, problem, subject):
        self._enter("set_up")
        await asyncio.sleep(self.delay)
        return await super().set_up(problem, subject)

    async def teach(self, request):
        self._enter("teach")
        await asyncio.sleep(self.delay)
        self.teach_requests.append(request)
        result = await super().teach(request)
        result.output.gap_repaired = request.teach_turns >= self.repair_after
        return result

    async def follow_up(self, request):
        self._enter("follow_up")
        await asyncio.sleep(self.delay)
        self.follow_up_requests.append(request)
        result = await super().follow_up(request)
        text = self.follow_up_texts.pop(0) if self.follow_up_texts else None
        if text is not None:  # None keeps the stub's own follow-up
            result.output.follow_up.problem = text
        return result

    async def judge(self, request):
        self._enter("judge")
        check = await super().judge(request)
        check.correct = self.correct
        return check


class Rig:
    def __init__(self, tutor=None, timeout=None):
        self.store = InMemoryHistory()
        seed_store(self.store)
        self.tutor = tutor or ScriptedTutor()
        service = SessionService(self.tutor, self.store, **({} if timeout is None else {"timeout": timeout}))
        self.service = service
        app.dependency_overrides[get_service] = lambda: service
        self.client = TestClient(app)

    def start(self, student_id, **extra):
        r = self.client.post(
            "/api/session", json={"problem": BALL, "student_id": str(student_id), **extra}
        )
        assert r.status_code == 200, r.text
        return r.json()["session_id"]

    def attempt(self, session_id, text="my idea"):
        r = self.client.post(f"/api/session/{session_id}/attempt", json={"text": text})
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def make_rig():
    yield Rig
    app.dependency_overrides.clear()
