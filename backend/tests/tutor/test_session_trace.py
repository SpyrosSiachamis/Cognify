"""The development session trace: every stage's evidence is recorded in order, provider failures stay apart from bad
output and verifier rejections, and tracing never changes what the tutor does.

The real SessionService and AgentTutor run here; only the model outputs are scripted.
"""

import asyncio
import json
import re
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from app.common.vocab import ModelOperation
from app.main import app
from app.seed.data import MARIA_ID, NIKOS_ID
from app.session.schema import SessionStartRequest
from app.tutor.agent import AgentTutor
from app.tutor.follow_up import follow_up_agent
from app.tutor.reasoning import reasoning_agent
from app.tutor.setup import setup_agent
from app.tutor.teaching import teaching_agent
from app.user.errors import ApiError
from app.user.router import get_service
from app.user.service import SessionService
from app.verification.agent import follow_up_checker, reply_checker, student_checker

from .fakes import APPROVE, FOLLOW_UP_OK, STUDENT_OK, FakeVerifier, ScriptedModel, sent_json
from .test_transfer_regressions import BOOKS, BOOKS_SETUP, COOKIES, FIRST, FRESH_ANSWER, REJECT, WRONG_DIVISION, proc

DRIFT = REJECT  # the verifier's method_drift rejection
REPAIRED = proc(("compute", "correct", "24 ÷ 6 = 4"), gap=None)
TAUGHT = "Let's draw 24 books as 6 equal rows. How many in each row?"
SECRET = "AKIA-SENTINEL-SECRET-0123456789"


class ProviderDown(ScriptedModel):
    """The follow-up generator gets a Bedrock 503; every other call is scripted as usual."""

    async def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "student_answers" in sent_json(messages):
            raise ModelHTTPError(503, "mistral.test", body={
                "Error": {"Code": "ServiceUnavailableException", "Message": "Bedrock is unable to process your request."},
                "ResponseMetadata": {"RequestId": "req-503", "HTTPStatusCode": 503, "RetryAttempts": 2,
                                     "HTTPHeaders": {"authorization": SECRET, "x-amzn-requestid": "req-503"}},
            })
        return await super().respond(messages, info)


def rig(store, diagnoses, replies, verifier_results, tracing=True, model_type=ScriptedModel, follow_ups=(COOKIES,),
        student_checks=(STUDENT_OK,)):
    model = model_type(diagnoses, replies=replies, setup=BOOKS_SETUP, follow_ups=list(follow_ups))
    verifier = FakeVerifier(*verifier_results, follow_up_checks=[FOLLOW_UP_OK], student_checks=list(student_checks))
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store, tracing=tracing)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=BOOKS, student_id=MARIA_ID))).session_id
    return svc, sid, model


def send(svc, sid, text):
    return asyncio.run(svc.attempt(sid, text))


def events(store, sid):
    return [(e.event_type, e.payload) for e in store.list_trace_events(sid)]


def of_type(store, sid, event_type):
    return [p for t, p in events(store, sid) if t == event_type]


def taught_then_verified(store, tracing=True):
    """First thought with a wrong division -> an approved teaching move -> repaired -> fresh problem -> VERIFIED."""
    svc, sid, model = rig(store, [WRONG_DIVISION, REPAIRED], replies=[TAUGHT], verifier_results=[APPROVE],
                          tracing=tracing)
    turns = [send(svc, sid, FIRST), send(svc, sid, "24 ÷ 6 = 4"), send(svc, sid, FRESH_ANSWER)]
    return svc, sid, turns


# ---- each stage is recorded ----


def test_session_start_is_recorded(store):
    _, sid, _ = rig(store, [WRONG_DIVISION], replies=["m"], verifier_results=[APPROVE])
    (kind, started), = [(t, p) for t, p in events(store, sid) if t != "MODEL_CALL"]
    assert kind == "SESSION_STARTED"
    assert (started.problem, started.phase, started.concept_state) == (BOOKS, "ask_first_thought", "untested")
    assert started.concept_name == BOOKS_SETUP["concept_name"] and started.solution_result == "4 books"
    setup_call = of_type(store, sid, "MODEL_CALL")[0]
    assert (setup_call.operation, setup_call.outcome, setup_call.provider) == ("tutor_setup", "ok", "function")


def test_student_response_reasoning_and_diagnosis_are_recorded(store):
    svc, sid, _ = rig(store, [WRONG_DIVISION], replies=[TAUGHT], verifier_results=[APPROVE])
    send(svc, sid, FIRST)
    response, = of_type(store, sid, "STUDENT_RESPONSE")
    assert (response.text, response.kind, response.problem, response.tutor_message) == (
        FIRST, "first_thought", BOOKS, None)
    assert response.counters.hints_used == 0 and response.practice_follow_up_id is None
    read, = of_type(store, sid, "REASONING_READ")
    assert (read.problem, read.attempt, read.final_answer, read.outcome) == (BOOKS, FIRST, "4 books", "ok")
    assert read.proposal["main_gap"] == "procedure"  # the model's own reading, before code's rules
    diagnosed, = of_type(store, sid, "DIAGNOSIS_RESULT")
    assert (diagnosed.kind, diagnosed.main_gap, diagnosed.mode, diagnosed.evidence) == (
        "initial", "procedure", "teach", "sufficient")
    assert diagnosed.method is not None and diagnosed.decision_mode is not None
    # The diagnosis exactly as teaching got it: its steps, with the student's own quotes.
    assert [s["status"] for s in diagnosed.diagnosis["steps"]] == ["correct", "wrong"]
    assert diagnosed.diagnosis["error"]["student_did"] == "divided 24 by 6 and got 5"


def test_an_approved_teaching_move_is_recorded_with_its_draft_and_check(store):
    svc, sid, _ = rig(store, [WRONG_DIVISION], replies=[TAUGHT], verifier_results=[APPROVE])
    send(svc, sid, FIRST)
    started, = of_type(store, sid, "TEACHING_GENERATION_STARTED")
    generated, = of_type(store, sid, "TEACHING_GENERATION_RESULT")
    checked, = of_type(store, sid, "VERIFIER_RESULT")
    sent, = of_type(store, sid, "REPLY_SENT")
    method = of_type(store, sid, "DIAGNOSIS_RESULT")[0].method
    assert (started.attempt, started.mode, started.method, started.main_gap) == (1, "teach", method, "procedure")
    assert (generated.outcome, generated.draft) == ("draft", TAUGHT)
    assert (checked.outcome, checked.checker, checked.draft, checked.method) == ("approved", "model", TAUGHT, method)
    assert (sent.kind, sent.message, sent.counts_as_hint, sent.shown_to_student) == ("teaching", TAUGHT, True, True)


def test_a_method_drift_rejection_can_be_reconstructed_down_to_the_fallback(store):
    """diagnosis -> teaching method -> generated draft -> verifier result -> fallback: all in order, nothing guessed."""
    # The scripted model answers a repeated input with the same reply: the 3rd try gets the 2nd's input (same reason
    # and note), so it repeats the 2nd draft.
    drafts = ["Draft one.", "Draft two.", "Draft two."]
    svc, sid, _ = rig(store, [WRONG_DIVISION], replies=drafts[:2], verifier_results=[DRIFT])
    turn = send(svc, sid, FIRST)
    assert turn.reply_check.outcome == "verifier_rejected"
    chain = [t for t, _ in events(store, sid) if t not in ("MODEL_CALL",)][1:]  # after SESSION_STARTED
    assert chain == ["STUDENT_RESPONSE", "REASONING_READ", "DIAGNOSIS_RESULT"] + [
        "TEACHING_GENERATION_STARTED", "TEACHING_GENERATION_RESULT", "VERIFIER_RESULT"] * 3 + [
        "TEACHING_FALLBACK", "STATE_TRANSITION", "REPLY_SENT"]
    diagnosed, = of_type(store, sid, "DIAGNOSIS_RESULT")
    checks = of_type(store, sid, "VERIFIER_RESULT")
    assert [(c.attempt, c.outcome, c.reason, c.draft) for c in checks] == [
        (i + 1, "verifier_rejected", "method_drift", d) for i, d in enumerate(drafts)]
    assert all(c.method == diagnosed.method and c.main_gap == diagnosed.main_gap for c in checks)
    assert checks[0].note == DRIFT["note"]
    # The rejection is reported as the verifier said it; who was at fault is left to the people reading it.
    assert "analysis" not in checks[0].model_dump()
    starts = of_type(store, sid, "TEACHING_GENERATION_STARTED")
    assert [s.retry_reason for s in starts] == [None, "method_drift", "method_drift"]  # passed back to the writer
    fallback, = of_type(store, sid, "TEACHING_FALLBACK")
    assert [(d.attempt, d.reason, d.draft) for d in fallback.drafts] == [
        (i + 1, "method_drift", d) for i, d in enumerate(drafts)]
    assert (fallback.last_reason, fallback.method, fallback.counts_as_hint) == ("method_drift", diagnosed.method, False)
    sent, = of_type(store, sid, "REPLY_SENT")
    assert (sent.kind, sent.message, sent.counts_as_hint) == ("safe_fallback", fallback.fallback_reply, False)
    assert sent.message == turn.message  # what the student saw


def test_a_bedrock_503_is_kept_apart_from_a_bad_output_and_from_the_users_error(store):
    """operation follow_up, provider bedrock-style 503, retryable; the student only sees model_unavailable."""
    svc, sid, _ = rig(store, [REPAIRED], replies=["m"], verifier_results=[APPROVE], model_type=ProviderDown)
    with pytest.raises(ApiError) as raised:
        send(svc, sid, "36 - 12 = 24 and 24 ÷ 6 = 4, so 4 books.")
    assert raised.value.body.code == "model_unavailable"
    call, = [c for c in of_type(store, sid, "MODEL_CALL") if c.operation == "tutor_follow_up"]
    assert (call.outcome, call.http_status, call.provider_error_code, call.request_id) == (
        "provider_http_error", 503, "ServiceUnavailableException", "req-503")
    assert (call.transient, call.sdk_retry_attempts) == (True, 2)
    generated, = of_type(store, sid, "FOLLOW_UP_RESULT")
    assert (generated.outcome, generated.failure) == ("generation_failed", "provider_error")
    error, = of_type(store, sid, "SESSION_ERROR")
    assert (error.operation, error.handled, error.api_status, error.api_code) == ("follow_up", False, 503,
                                                                                  "model_unavailable")
    assert error.causes[0]["type"] == "FollowUpUnavailable"


def test_an_invalid_follow_up_output_is_not_reported_as_a_provider_failure(store):
    svc, sid, _ = rig(store, [REPAIRED], replies=["m"], verifier_results=[APPROVE], follow_ups=[{"nonsense": 1}])
    with pytest.raises(ApiError):
        send(svc, sid, "36 - 12 = 24 and 24 ÷ 6 = 4, so 4 books.")
    call, = [c for c in of_type(store, sid, "MODEL_CALL") if c.operation == "tutor_follow_up"]
    assert (call.outcome, call.http_status, call.transient) == ("invalid_output", None, None)
    assert "retries" in (call.detail or "")
    assert of_type(store, sid, "FOLLOW_UP_RESULT")[0].failure == "invalid_output"
    assert of_type(store, sid, "SESSION_ERROR")[0].operation == "follow_up"


def test_a_call_stopped_by_the_turn_time_limit_is_recorded_as_cancelled(store):
    model = ScriptedModel([WRONG_DIVISION], replies=[TAUGHT], setup=BOOKS_SETUP, follow_ups=[COOKIES])
    verifier = FakeVerifier(APPROVE, follow_up_checks=[FOLLOW_UP_OK])
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store, timeout=0.05, tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=BOOKS, student_id=MARIA_ID))).session_id
    model.delay = 1.0  # every model call is now slower than the turn limit
    assert send(svc, sid, FIRST).reply_check.outcome == "turn_failed"
    call = of_type(store, sid, "MODEL_CALL")[-1]
    assert (call.operation, call.outcome) == ("tutor_reasoning", "cancelled")
    error, = of_type(store, sid, "SESSION_ERROR")
    assert (error.operation, error.handled, error.error_type) == ("teach", True, "TimeoutError")


def test_the_successful_transfer_path_is_reconstructable(store):
    """diagnosis -> teaching -> support removal -> fresh problem -> transfer verification -> session end."""
    _, sid, turns = taught_then_verified(store)
    assert turns[-1].verdict.result == "VERIFIED"
    kinds = [t for t, _ in events(store, sid) if t in (
        "DIAGNOSIS_RESULT", "REPLY_SENT", "SUPPORT_REMOVED", "FRESH_PROBLEM_GENERATED", "TRANSFER_RESULT",
        "SESSION_ENDED")]
    assert kinds == ["DIAGNOSIS_RESULT", "REPLY_SENT", "DIAGNOSIS_RESULT", "SUPPORT_REMOVED", "FRESH_PROBLEM_GENERATED",
                     "REPLY_SENT", "TRANSFER_RESULT", "REPLY_SENT", "SESSION_ENDED"]
    removed, = of_type(store, sid, "SUPPORT_REMOVED")
    method = of_type(store, sid, "DIAGNOSIS_RESULT")[0].method
    assert (removed.reason, removed.method, removed.counters.hints_used) == ("gap_repaired", method, 1)
    fresh, = of_type(store, sid, "FRESH_PROBLEM_GENERATED")
    assert (fresh.problem, fresh.support_removed, fresh.hints_available) == (COOKIES["problem"], True, False)
    transfer, = of_type(store, sid, "TRANSFER_RESULT")
    assert (transfer.follow_up_id, transfer.student_text, transfer.verified, transfer.independent) == (
        fresh.follow_up_id, FRESH_ANSWER, True, True)
    assert (transfer.gap_credited, transfer.method_credited) == ("procedure", method)
    assert transfer.strategy_independent_successes_after == transfer.strategy_independent_successes_before + 1
    assert (transfer.concept_before, transfer.concept_after) == ("untested", "verified")
    ended, = of_type(store, sid, "SESSION_ENDED")
    assert (ended.reason, ended.status, ended.verified, ended.transfer_attempts) == ("verified", "verified", True, 1)


def test_state_transitions_are_recorded_with_their_trigger_and_counters(store):
    _, sid, _ = taught_then_verified(store)
    moves = [(t.previous_phase, t.trigger, t.new_phase) for t in of_type(store, sid, "STATE_TRANSITION")]
    assert moves == [("ask_first_thought", "first_answer", "teach"), ("teach", "gap_repaired", "stress_test"),
                     ("stress_test", "verified", "verdict")]
    last = of_type(store, sid, "STATE_TRANSITION")[-1]
    assert (last.status, last.counters.transfer_attempts, last.counters.hints_used) == ("verified", 1, 1)


def test_a_not_yet_and_the_practice_problem_are_recorded(store):
    svc, sid, _ = rig(store, [REPAIRED], replies=["m"], verifier_results=[APPROVE],
                      student_checks=[{**STUDENT_OK, "correct": False}])
    send(svc, sid, "36 - 12 = 24 and 24 ÷ 6 = 4, so 4 books.")
    send(svc, sid, "50 - 14 = 36, 36 ÷ 4 = 8.")
    transfer, = of_type(store, sid, "TRANSFER_RESULT")
    fresh, = of_type(store, sid, "FRESH_PROBLEM_GENERATED")
    assert (transfer.verified, transfer.not_yet_reason, transfer.session_over) == (False, "incorrect", False)
    assert transfer.practice_follow_up_id == fresh.follow_up_id
    move = of_type(store, sid, "STATE_TRANSITION")[-1]
    assert (move.trigger, move.new_phase, move.practice_follow_up_id) == ("not_yet", "teach", fresh.follow_up_id)
    send(svc, sid, "I don't know")
    response = of_type(store, sid, "STUDENT_RESPONSE")[-1]
    assert (response.problem, response.practice_follow_up_id) == (COOKIES["problem"], fresh.follow_up_id)


def test_exit_ends_the_session_in_the_trace(store):
    svc, sid, _ = rig(store, [WRONG_DIVISION], replies=[TAUGHT], verifier_results=[APPROVE])
    send(svc, sid, FIRST)
    asyncio.run(svc.exit(sid))
    move, = [t for t in of_type(store, sid, "STATE_TRANSITION") if t.trigger == "exit"]
    ended, = of_type(store, sid, "SESSION_ENDED")
    assert (move.previous_phase, move.new_phase) == ("teach", "exited")
    assert (ended.reason, ended.status, ended.verified) == ("exit", "exited", False)


# ---- ordering, separation, privacy, and no change in behaviour ----


def test_events_are_numbered_in_order_and_grouped_by_turn(store):
    _, sid, _ = taught_then_verified(store)
    trace = store.list_trace_events(sid)
    assert [e.sequence for e in trace] == list(range(len(trace)))
    assert [e.turn for e in trace] == sorted(e.turn for e in trace) and trace[-1].turn == 3  # start + 3 attempts
    assert all(a.at <= b.at for a, b in zip(trace, trace[1:]))
    assert len({e.id for e in trace}) == len(trace)


def test_traces_of_sessions_running_at_the_same_time_do_not_mix(store):
    model = ScriptedModel([WRONG_DIVISION], replies=[TAUGHT], setup=BOOKS_SETUP, follow_ups=[COOKIES], delay=0.01)
    verifier = FakeVerifier(APPROVE, follow_up_checks=[FOLLOW_UP_OK])
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store, tracing=True)

    async def both():
        starts = await asyncio.gather(*(svc.start(SessionStartRequest(problem=BOOKS, student_id=s))
                                        for s in (MARIA_ID, NIKOS_ID)))
        ids = [s.session_id for s in starts]
        await asyncio.gather(*(svc.attempt(i, f"{FIRST} ({n})") for n, i in enumerate(ids)))
        return ids

    maria, nikos = asyncio.run(both())
    for n, sid in enumerate((maria, nikos)):
        trace = store.list_trace_events(sid)
        assert {e.session_id for e in trace} == {sid}
        assert [p.text for t, p in events(store, sid) if t == "STUDENT_RESPONSE"] == [f"{FIRST} ({n})"]
        assert len(of_type(store, sid, "DIAGNOSIS_RESULT")) == 1 and len(of_type(store, sid, "SESSION_STARTED")) == 1


def test_no_credentials_or_headers_reach_the_trace(store, monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", SECRET)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", SECRET)
    svc, sid, _ = rig(store, [REPAIRED], replies=["m"], verifier_results=[APPROVE], model_type=ProviderDown)
    with pytest.raises(ApiError):
        send(svc, sid, "36 - 12 = 24 and 24 ÷ 6 = 4, so 4 books.")
    dumped = json.dumps([e.model_dump(mode="json") for e in store.list_trace_events(sid)]).lower()
    assert SECRET.lower() not in dumped
    assert "authorization" not in dumped and "httpheaders" not in dumped and "aws_secret" not in dumped


def test_tracing_changes_nothing_the_student_or_history_sees(store):
    from app.history import InMemoryHistory
    from app.seed import seed_store

    other = InMemoryHistory()
    seed_store(other)
    _, traced_id, traced = taught_then_verified(store, tracing=True)
    _, plain_id, plain = taught_then_verified(other, tracing=False)
    uuid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    def seen(turns):  # what the student got back, with the random ids taken out
        return [uuid.sub("<id>", t.model_dump_json()) for t in turns]

    assert len(seen(traced)) == 3 and seen(traced) == seen(plain)
    assert other.list_trace_events(plain_id) == []
    a, b = store.get_session(traced_id), other.get_session(plain_id)
    same = {"phase", "status", "hints_used", "teach_turns", "not_yet_count", "last_reply_taught", "last_tutor_message"}
    assert a.model_dump(include=same) == b.model_dump(include=same)
    assert [d.outcome for d in store.list_reply_drafts(traced_id)] == [d.outcome for d in other.list_reply_drafts(plain_id)]


def test_every_agent_is_a_known_model_operation():
    agents = (setup_agent, reasoning_agent, teaching_agent, follow_up_agent, reply_checker, follow_up_checker,
              student_checker)
    assert sorted(a.name for a in agents) == sorted(get_args(ModelOperation))


# ---- inspection ----


def test_the_trace_endpoints_are_off_unless_tracing_is_on(store):
    svc, sid, _ = rig(store, [WRONG_DIVISION], replies=["m"], verifier_results=[APPROVE], tracing=False)
    app.dependency_overrides[get_service] = lambda: svc
    try:
        client = TestClient(app)
        for path in (f"/api/session/{sid}/debug-trace", "/api/debug-trace", "/api/debug-trace/export"):
            assert client.get(path).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_a_session_and_several_sessions_can_be_exported(store):
    svc, sid, _ = taught_then_verified(store)
    other = asyncio.run(svc.start(SessionStartRequest(problem=BOOKS, student_id=NIKOS_ID))).session_id
    app.dependency_overrides[get_service] = lambda: svc
    try:
        client = TestClient(app)
        one = client.get(f"/api/session/{sid}/debug-trace").json()
        assert one["session_id"] == str(sid)
        assert [e["sequence"] for e in one["events"]] == list(range(len(one["events"])))
        assert one["events"][0]["event_type"] == "MODEL_CALL" and one["events"][1]["event_type"] == "SESSION_STARTED"
        index = client.get("/api/debug-trace").json()["sessions"]
        assert [(r["session_id"], r["status"]) for r in index] == [(str(sid), "verified"), (str(other), "active")]
        export = client.get("/api/debug-trace/export").json()
        assert [s["session_id"] for s in export["sessions"]] == [str(sid), str(other)]
        picked = client.get("/api/debug-trace/export", params={"session_id": str(other)}).json()
        assert [s["session_id"] for s in picked["sessions"]] == [str(other)]
    finally:
        app.dependency_overrides.clear()
