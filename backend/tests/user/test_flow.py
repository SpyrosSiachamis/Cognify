import asyncio
from uuid import UUID

from app.main import app
from app.seed.data import KINEMATICS_ID, MARIA_ID, NIKOS_ID
from app.user.router import get_service
from tests.user.conftest import BALL, ScriptedTutor


def test_health_both_paths(make_rig):
    client = make_rig().client
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}


def test_maria_story_end_to_end(make_rig):
    rig = make_rig()
    r = rig.client.post("/api/session", json={"problem": BALL, "student_id": str(MARIA_ID)})
    assert r.json()["phase"] == "ask_first_thought" and r.json()["hints_used"] == 0
    sid = r.json()["session_id"]

    t1 = rig.attempt(sid, "I found the time, 2.04 s, but not the height.")
    assert t1["phase"] == "teach" and t1["hints_used"] == 0
    assert t1["diagnosis"]["main_gap"] == "recognition"
    assert t1["method"]["name"] == "visual_decomposition" and t1["method"]["experiment"] is False

    t2 = rig.attempt(sid, "I sketched it: the speed is 0 at the top.")
    assert t2["phase"] == "stress_test" and t2["hints_used"] == 1
    assert "balcony" in t2["follow_up"]["problem"]

    t3 = rig.attempt(sid, "Used v^2 = u^2 - 2gh, about 11.5 m.")
    assert t3["phase"] == "verdict" and t3["session_over"] is True
    assert t3["verdict"]["result"] == "VERIFIED" and t3["verdict"]["independent"] is True
    changes = t3["verdict"]["changes"]
    assert changes["concept"]["name"] == "Constant-acceleration kinematics"
    assert (changes["concept"]["before"], changes["concept"]["after"]) == ("fragile", "verified")
    assert changes["strategy"]["before"] == {"uses": 9, "independent_successes": 7}
    assert changes["strategy"]["after"] == {"uses": 10, "independent_successes": 8}
    assert rig.store.get_session(UUID(sid)).status == "verified"


def test_nothing_hidden_leaves_the_backend(make_rig):
    rig = make_rig()
    sid = rig.start(MARIA_ID)
    bodies = [rig.attempt(sid) for _ in range(3)]
    text = str(bodies)
    assert "hidden" not in text and "rubric" not in text and "20.4" not in text


def test_nikos_gets_a_different_path(make_rig):
    rig = make_rig()
    sid = rig.start(NIKOS_ID)
    t1 = rig.attempt(sid, "I used v^2 = u^2 - 2gh and got h = -20.4 m")
    assert t1["diagnosis"]["main_gap"] == "procedure"
    assert t1["method"]["name"] == "worked_example"
    t2 = rig.attempt(sid)
    assert "downward" in t2["follow_up"]["problem"]


def test_views_update_after_verification(make_rig):
    rig = make_rig()
    sid = rig.start(MARIA_ID)
    for _ in range(3):
        rig.attempt(sid)
    learner = rig.client.get(f"/api/learner/{MARIA_ID}").json()
    assert learner["is_seeded"] is True
    assert learner["concepts"][0]["state"] == "verified"
    strategies = rig.client.get(f"/api/strategies/{MARIA_ID}").json()
    row = next(r for r in strategies["rows"] if r["method"] == "visual_decomposition")
    assert (row["uses"], row["independent_successes"]) == (10, 8)
    total = next(m for m in strategies["methods"] if m["method"] == "visual_decomposition")
    assert (total["uses"], total["independent_successes"]) == (10, 8)


def test_history_records_everything_as_it_happens(make_rig):
    rig = make_rig()
    sid = rig.start(MARIA_ID)
    rig.attempt(sid)
    attempts = rig.store.list_attempts(UUID(sid))
    assert len(attempts) == 1 and attempts[0].phase == "ask_first_thought"
    assert [s.role for s in rig.store.list_steps(attempts[0].id)] == ["identify_quantities", "choose_method"]
    assert rig.store.latest_diagnosis(UUID(sid)).main_gap == "recognition"
    decision = rig.store.latest_strategy_decision(UUID(sid))
    assert (decision.method, decision.decision_mode) == ("visual_decomposition", "best_known")
    rig.attempt(sid)
    assert rig.store.latest_follow_up(UUID(sid)).hidden_rubric  # saved, never returned


def test_exit_records_nothing_and_ends_the_session(make_rig):
    rig = make_rig()
    sid = rig.start(MARIA_ID)
    r = rig.client.post(f"/api/session/{sid}/exit")
    assert r.json()["phase"] == "exited" and r.json()["evidence_recorded"] is False
    assert r.json()["solution"]["result"] == "20.4 m"
    assert rig.store.get_session(UUID(sid)).status == "exited"
    stats = {(s.gap_type, s.method): s for s in rig.store.strategy_stats(MARIA_ID)}
    assert stats["recognition", "visual_decomposition"].uses == 9
    assert rig.store.get_concept_state(MARIA_ID, KINEMATICS_ID).state == "fragile"
    r = rig.client.post(f"/api/session/{sid}/attempt", json={"text": "hello"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_over"


def test_blank_text_asks_a_question_and_changes_nothing(make_rig):
    tutor = ScriptedTutor()
    rig = make_rig(tutor)
    sid = rig.start(MARIA_ID)
    calls_before = tutor.calls
    t = rig.attempt(sid, "   ")
    assert t["phase"] == "ask_first_thought" and t["hints_used"] == 0
    assert tutor.calls == calls_before and rig.store.list_attempts(UUID(sid)) == []


def test_two_not_yet_verdicts_end_the_session_without_credit(make_rig):
    tutor = ScriptedTutor(correct=False)
    rig = make_rig(tutor)
    sid = rig.start(MARIA_ID)
    rig.attempt(sid)
    assert rig.attempt(sid)["phase"] == "stress_test"

    first = rig.attempt(sid)
    assert first["verdict"]["result"] == "NOT YET" and first["session_over"] is False
    assert first["verdict"]["remaining_gap"] == "recognition"

    assert rig.attempt(sid)["phase"] == "teach"  # re-diagnosis after the first NOT YET
    assert tutor.teach_requests[-1].after_not_yet is True
    assert rig.attempt(sid)["phase"] == "stress_test"

    second = rig.attempt(sid)
    assert second["verdict"]["result"] == "NOT YET" and second["session_over"] is True
    stats = {(s.gap_type, s.method): s for s in rig.store.strategy_stats(MARIA_ID)}
    stat = stats["recognition", "visual_decomposition"]
    assert (stat.uses, stat.independent_successes) == (11, 7)
    assert rig.store.get_session(UUID(sid)).status == "not_yet_ended"
    r = rig.client.post(f"/api/session/{sid}/attempt", json={"text": "more"})
    assert r.status_code == 409


def test_lucky_correct_answer_after_many_hints_is_not_verified(make_rig):
    rig = make_rig(ScriptedTutor(repair_after=99))  # only the teaching cap ends teaching
    sid = rig.start(MARIA_ID)
    for _ in range(3):
        assert rig.attempt(sid)["phase"] == "teach"
    t = rig.attempt(sid)
    assert t["phase"] == "stress_test" and t["hints_used"] == 3
    v = rig.attempt(sid, "11.5 m")["verdict"]
    assert v["result"] == "NOT YET" and v["independent"] is False


def test_force_experiment_flag_reaches_the_agent(make_rig):
    tutor = ScriptedTutor()
    rig = make_rig(tutor)
    sid = rig.start(MARIA_ID, force_experiment=True)
    rig.attempt(sid)
    assert tutor.teach_requests[0].force_experiment is True


def test_repeated_follow_up_is_regenerated(make_rig):
    tutor = ScriptedTutor(follow_up_texts=[BALL, "A stone is dropped from a 45 m cliff. How fast does it land?"])
    rig = make_rig(tutor)
    sid = rig.start(MARIA_ID)
    rig.attempt(sid)
    t = rig.attempt(sid)
    assert "stone" in t["follow_up"]["problem"]
    assert [r.retry_reason for r in tutor.follow_up_requests][0] is None
    assert tutor.follow_up_requests[1].retry_reason


def test_follow_up_that_keeps_repeating_gives_a_retryable_error(make_rig):
    rig = make_rig(ScriptedTutor(follow_up_texts=[BALL, BALL, BALL]))
    sid = rig.start(MARIA_ID)
    rig.attempt(sid)
    r = rig.client.post(f"/api/session/{sid}/attempt", json={"text": "x"})
    assert r.status_code == 503 and r.json()["error"]["retryable"] is True


def test_agent_failures_never_become_a_500(make_rig):
    # teaching: safe fallback, nothing saved, nothing counted
    rig = make_rig(ScriptedTutor(fail={"teach"}))
    sid = rig.start(MARIA_ID)
    t = rig.attempt(sid)
    assert t["phase"] == "ask_first_thought" and t["reply_check"]["approved"] is False
    assert rig.store.list_attempts(UUID(sid)) == [] and rig.store.get_session(UUID(sid)).teach_turns == 0
    # session start and judging: a retryable error
    rig = make_rig(ScriptedTutor(fail={"set_up"}))
    r = rig.client.post("/api/session", json={"problem": BALL, "student_id": str(MARIA_ID)})
    assert r.status_code == 503 and r.json()["error"]["retryable"] is True
    rig = make_rig(ScriptedTutor(fail={"judge"}))
    sid = rig.start(MARIA_ID)
    rig.attempt(sid)
    rig.attempt(sid)
    r = rig.client.post(f"/api/session/{sid}/attempt", json={"text": "answer"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"


def test_unknown_student_and_session(make_rig):
    rig = make_rig()
    ghost = "11111111-1111-4111-8111-111111111111"
    r = rig.client.post("/api/session", json={"problem": BALL, "student_id": ghost})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_student"
    r = rig.client.post(f"/api/session/{ghost}/attempt", json={"text": "x"})
    assert r.status_code == 404 and r.json()["error"]["retryable"] is False
    assert rig.client.get(f"/api/learner/{ghost}").status_code == 404


def test_rerunning_the_story_never_repeats_a_follow_up(make_rig):
    rig = make_rig()
    problems = []
    for _ in range(3):
        sid = rig.start(MARIA_ID)
        rig.attempt(sid)
        problems.append(rig.attempt(sid)["follow_up"]["problem"])
        rig.attempt(sid)
    assert len(set(problems)) == 3


# ---- hardening: error shape, double clicks, slow agent ----


def _is_contract_error(body: dict) -> bool:
    return set(body) == {"error"} and set(body["error"]) == {"code", "message", "retryable"}


def test_every_error_uses_the_contract_shape(make_rig):
    rig = make_rig()
    sid = rig.start(MARIA_ID)
    cases = [
        rig.client.post(f"/api/session/{sid}/attempt", json={"text": "x", "extra": 1}),  # unknown field
        rig.client.post(f"/api/session/{sid}/attempt", json={}),  # missing field
        rig.client.post("/api/session/not-a-uuid/attempt", json={"text": "x"}),  # bad path value
        rig.client.post("/api/session", json={"problem": "a" * 2001, "student_id": str(MARIA_ID)}),
        rig.client.get("/api/nope"),  # unknown route
        rig.client.get("/api/session"),  # wrong method
    ]
    for r in cases:
        assert r.status_code in (404, 405, 422), r.text
        assert _is_contract_error(r.json()), r.text
    assert cases[0].json()["error"]["code"] == "invalid_request"
    assert cases[4].json()["error"]["code"] == "not_found"


def test_validation_error_never_echoes_the_submitted_text(make_rig):
    rig = make_rig()
    secret = "my private answer " * 300  # over the length cap, so it is rejected
    r = rig.client.post("/api/session", json={"problem": secret, "student_id": str(MARIA_ID)})
    assert r.status_code == 422 and "private" not in r.text


def test_unexpected_bug_becomes_a_contract_error_not_a_traceback(make_rig):
    class Buggy(ScriptedTutor):
        async def judge(self, request):
            raise KeyError("a bug that is not an agent failure")

    rig = make_rig(Buggy())
    sid = rig.start(MARIA_ID)
    rig.attempt(sid)
    rig.attempt(sid)
    r = rig.client.post(f"/api/session/{sid}/attempt", json={"text": "answer"})
    assert r.status_code == 503 and _is_contract_error(r.json())  # agent failures are retryable 503s


def _post_concurrently(rig, requests):
    """Send the requests at the same moment through the real ASGI app; returns the responses in order."""
    import httpx

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await asyncio.gather(*(client.post(url, json=body) for url, body in requests))

    return asyncio.run(run())


def test_double_click_on_a_slow_agent_runs_the_turns_one_after_the_other(make_rig):
    tutor = ScriptedTutor()
    tutor.delay = 0.05
    rig = make_rig(tutor)
    sid = rig.start(MARIA_ID)
    url = f"/api/session/{sid}/attempt"
    first, second = _post_concurrently(rig, [(url, {"text": "idea one"}), (url, {"text": "idea two"})])
    assert first.status_code == second.status_code == 200
    # Without the lock both would read the first-thought state and the counters would be 1, not 2
    assert sorted(r.json()["phase"] for r in (first, second)) == ["stress_test", "teach"]
    session = rig.store.get_session(UUID(sid))
    assert (session.teach_turns, session.hints_used) == (2, 1)
    assert [a.phase for a in rig.store.list_attempts(UUID(sid))] == ["ask_first_thought", "teach"]


def test_exit_waits_for_a_turn_that_is_still_running(make_rig):
    tutor = ScriptedTutor()
    tutor.delay = 0.05
    rig = make_rig(tutor)
    sid = rig.start(MARIA_ID)
    attempt, leave = _post_concurrently(
        rig, [(f"/api/session/{sid}/attempt", {"text": "idea"}), (f"/api/session/{sid}/exit", None)]
    )
    assert attempt.status_code == 200 and leave.status_code == 200
    assert rig.store.get_session(UUID(sid)).status == "exited"
    assert len(rig.store.list_attempts(UUID(sid))) == 1  # the turn that was running was not lost
    assert rig.store.get_session(UUID(sid)).hidden_solution is not None


def test_a_slow_agent_becomes_the_safe_fallback_not_a_hang(make_rig):
    tutor = ScriptedTutor()
    rig = make_rig(tutor, timeout=0.05)
    sid = rig.start(MARIA_ID)
    tutor.delay = 1.0  # from now on every agent call is slower than the limit
    t = rig.attempt(sid)
    assert t["phase"] == "ask_first_thought" and t["reply_check"]["approved"] is False
    assert rig.store.list_attempts(UUID(sid)) == [] and rig.store.get_session(UUID(sid)).teach_turns == 0


def test_a_slow_agent_at_session_start_is_a_retryable_error(make_rig):
    tutor = ScriptedTutor()
    tutor.delay = 1.0
    rig = make_rig(tutor, timeout=0.05)
    r = rig.client.post("/api/session", json={"problem": BALL, "student_id": str(MARIA_ID)})
    assert r.status_code == 503 and r.json()["error"]["retryable"] is True


def test_finished_sessions_do_not_keep_their_lock(make_rig):
    rig = make_rig()
    service = app.dependency_overrides[get_service]()
    for _ in range(3):
        sid = rig.start(MARIA_ID)
        for _ in range(3):
            rig.attempt(sid)
    assert service._locks == {}


def test_agent_failures_are_logged_not_swallowed(make_rig, caplog):
    rig = make_rig(ScriptedTutor(fail={"teach"}))
    sid = rig.start(MARIA_ID)
    with caplog.at_level("WARNING", logger="app.user.service"):
        rig.attempt(sid)
    assert any("teach failed" in r.message and r.exc_info for r in caplog.records)


def test_malformed_json_is_a_readable_contract_error(make_rig):
    r = make_rig().client.post("/api/session", content="{bad json", headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["message"].startswith("request body:")
