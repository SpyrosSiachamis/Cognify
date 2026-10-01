"""SessionService (user module) driving the real AgentTutor with scripted models.

Covers the contract changes: no gap -> stress test, probe -> no method recorded,
repair decided from the previous turn's steps, and a verdict without a method.
"""

import asyncio

from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest, VerdictTurn
from app.tutor.agent import AgentTutor
from app.user.service import SessionService

from .conftest import PROBLEM
from .fakes import FakeVerifier, ScriptedModel, diagnosis

STALL = diagnosis(("compute", "correct", "2.04 s"), ("choose_method", "missing", None), gap="recognition")
FOUND = diagnosis(("compute", "correct", "2.04 s"), ("choose_method", "correct", "v^2 = u^2 - 2gh"))
CORRECT = diagnosis(("choose_method", "correct", "v^2 = u^2 - 2gh"), ("compute", "correct", "h = 20.4 m"), gap=None)
NOTHING = diagnosis(("choose_method", "missing", None), gap=None, confidence="low", evidence="insufficient")


def service(store, *diagnoses):
    model = ScriptedModel(list(diagnoses))
    return SessionService(AgentTutor(store, model.model, FakeVerifier().model), store), model


def start(svc):
    return asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id


def send(svc, session_id, text):
    return asyncio.run(svc.attempt(session_id, text))


def test_correct_first_thought_goes_straight_to_the_stress_test(store):
    svc, model = service(store, CORRECT)
    sid = start(svc)
    turn = send(svc, sid, "I used v^2 = u^2 - 2gh, so h = 20.4 m.")
    assert turn.phase == "stress_test" and turn.follow_up is not None
    assert model.teaching_calls == 0
    assert store.latest_strategy_decision(sid) is None  # nothing was taught, nothing recorded


def test_verdict_without_a_method_credits_no_strategy(store):
    svc, _ = service(store, CORRECT)
    sid = start(svc)
    send(svc, sid, "I used v^2 = u^2 - 2gh, so h = 20.4 m.")
    before = {(s.gap_type, s.method): s.uses for s in store.strategy_stats(MARIA_ID)}
    verdict = send(svc, sid, "v^2 = u^2 - 2gh with u = 15, so h = 11.5 m.")
    assert isinstance(verdict, VerdictTurn) and verdict.verdict.result == "VERIFIED"
    assert verdict.verdict.changes.strategy is None
    assert {(s.gap_type, s.method): s.uses for s in store.strategy_stats(MARIA_ID)} == before


def test_probe_records_no_method(store):
    svc, model = service(store, NOTHING)
    sid = start(svc)
    turn = send(svc, sid, "I don't know.")
    assert turn.phase == "teach" and turn.method is None
    assert turn.diagnosis.main_gap is None
    assert store.latest_strategy_decision(sid) is None
    assert model.teaching_inputs[0]["mode"] == "probe"


def test_repair_is_detected_from_the_previous_turn(store):
    svc, model = service(store, STALL, FOUND)
    sid = start(svc)
    first = send(svc, sid, "I found the time, about 2.04 s, but not the height.")
    assert first.phase == "teach" and first.method.name == "visual_decomposition"
    second = send(svc, sid, "With 2.04 s known I could use v^2 = u^2 - 2gh instead.")
    assert second.phase == "stress_test"  # code saw choose_method go from missing to correct
    assert model.teaching_calls == 1  # no extra teaching after the repair


def test_repaired_session_credits_the_method_that_taught_it(store):
    svc, _ = service(store, STALL, FOUND)
    sid = start(svc)
    send(svc, sid, "I found the time, about 2.04 s, but not the height.")
    send(svc, sid, "With 2.04 s known I could use v^2 = u^2 - 2gh instead.")
    verdict = send(svc, sid, "v^2 = u^2 - 2gh with u = 15, so h = 11.5 m.")
    change = verdict.verdict.changes.strategy
    assert (change.gap, change.method) == ("recognition", "visual_decomposition")
    assert (change.before.uses, change.after.uses) == (9, 10)
