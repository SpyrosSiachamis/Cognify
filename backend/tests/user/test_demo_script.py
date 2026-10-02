"""demo/play_story.py against the real app on a real port, so the rehearsal script cannot rot."""

import importlib.util
import os
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app.history import InMemoryHistory
from app.main import app
from app.seed import seed_store
from app.user.router import get_service
from app.user.service import SessionService
from tests.user.conftest import ScriptedTutor

SCRIPT = Path(__file__).resolve().parents[3] / "demo" / "play_story.py"

pytestmark = pytest.mark.skipif(
    bool(os.environ.get("TUTOR_MODEL_ID")), reason="the exact story needs the stub tutor (TUTOR_MODEL_ID is set)"
)


def load_script():
    spec = importlib.util.spec_from_file_location("play_story", SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _serve(tutor=None):
    """A real server on a real port. With a tutor, the app serves that tutor on a fresh seeded history."""
    app.dependency_overrides.clear()
    if tutor is not None:
        store = InMemoryHistory()
        seed_store(store)
        service = SessionService(tutor, store)
        app.dependency_overrides[get_service] = lambda: service
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "the test server did not start"
    return server, thread, f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"


@pytest.fixture
def live_url():
    server, thread, url = _serve()
    yield url
    server.should_exit = True
    thread.join(timeout=10)
    app.dependency_overrides.clear()


@pytest.fixture
def serve_tutor():
    """serve_tutor(tutor) -> url of a server that uses that tutor."""
    started = []

    def start(tutor):
        server, thread, url = _serve(tutor)
        started.append((server, thread))
        return url

    yield start
    for server, thread in started:
        server.should_exit = True
        thread.join(timeout=10)
    app.dependency_overrides.clear()


def test_the_story_script_passes_against_the_app(live_url, capsys):
    assert load_script().main(["--base-url", live_url]) == 0, capsys.readouterr().out


def test_the_script_can_be_run_twice_in_a_row(live_url, capsys):
    script = load_script()
    assert script.main(["--base-url", live_url, "--shape-only"]) == 0, capsys.readouterr().out
    assert script.main(["--base-url", live_url]) == 0, capsys.readouterr().out


def test_the_script_refuses_a_remote_address(capsys):
    assert load_script().main(["--base-url", "https://demo.example.com"]) == 2
    assert "Refusing" in capsys.readouterr().out


def test_the_script_reports_an_unreachable_backend(capsys):
    assert load_script().main(["--base-url", "http://127.0.0.1:9"]) == 2


# ---- the real model writes its own follow-up, so the verdict can be either one ----


def test_shape_only_reports_which_verdict_it_got(serve_tutor, capsys):
    url = serve_tutor(ScriptedTutor(correct=False))
    code = load_script().main(["--base-url", url, "--shape-only", "--student", "maria"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "verdict: NOT YET, session continues" in out
    assert "strategy counts moved by one use, and one success only if VERIFIED" in out


def test_the_exact_story_still_demands_verified(serve_tutor, capsys):
    url = serve_tutor(ScriptedTutor(correct=False))
    assert load_script().main(["--base-url", url, "--student", "maria"]) == 1
    assert "FAIL  VERIFIED, decided by code" in capsys.readouterr().out


def test_a_retryable_503_is_retried_and_costs_no_hint(serve_tutor, capsys):
    url = serve_tutor(ScriptedTutor(fail_once={"follow_up"}))
    code = load_script().main(["--base-url", url, "--shape-only", "--student", "maria"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "retryable), trying again with the same answer" in out
    assert "PASS  a retried request did not cost an extra hint" in out


def test_the_script_notices_when_a_retry_costs_an_extra_hint(serve_tutor, capsys, monkeypatch):
    # Break the backend fix on purpose: forget that a follow-up is owed, so the retry teaches again
    class NeverOwed(dict):
        def __contains__(self, key):
            return False

    original = SessionService.__init__

    def broken_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self._follow_up_owed = NeverOwed()

    # A turn that moves on is never counted as help, so also count the failed one as a delivered move;
    # otherwise teaching again would be free and the script would have nothing to notice
    original_stress = SessionService._stress_test

    async def broken_stress(self, session, main_gap):
        try:
            return await original_stress(self, session, main_gap)
        except Exception:
            session.last_reply_taught = True
            self._store.update_session(session)
            raise

    monkeypatch.setattr(SessionService, "__init__", broken_init)
    monkeypatch.setattr(SessionService, "_stress_test", broken_stress)
    url = serve_tutor(ScriptedTutor(fail_once={"follow_up"}))
    code = load_script().main(["--base-url", url, "--shape-only", "--student", "maria"])
    out = capsys.readouterr().out
    assert code == 1 and "FAIL  a retried request did not cost an extra hint" in out, out


# ---- the leak check must tell a tutor repeating the student from a tutor giving the answer away ----


def _leak_check(student_wrote: list[str], tutor_message: str, **extra) -> list[str]:
    run = load_script().Run("http://unused", shape_only=False)
    run.written = student_wrote
    run.no_leaks("turn", {"message": tutor_message, **extra})
    return run.failures


def test_a_tutor_quoting_the_students_own_step_is_not_a_leak():
    # What the real model really did: it quoted Nikos's correct step back to him
    wrote = ["The acceleration is -9.8, v = 0 at the top, so 0 = 400 - 19.6 h and h = 400 / 19.6."]
    assert _leak_check(wrote, 'Not yet: one step does not hold up yet: "h = 400 / 19.6". Look at that step again.') == []
    assert _leak_check(["I got h = -20.4 m"], "You wrote h = -20.4 m. What sign should the height have?") == []


def test_stating_the_answer_is_still_a_leak_even_if_the_student_wrote_something_close():
    # Nikos wrote "-20.4 m" himself; a tutor saying the height IS 20.4 m must still be caught
    assert _leak_check(["I got h = -20.4 m"], "The height is h = 20.4 m, so your sign was wrong.") == ["turn: nothing hidden or solved is shown"]
    assert _leak_check([], "The ball rises 20.4 m.") == ["turn: nothing hidden or solved is shown"]
    assert _leak_check(["I found the time, 2.04 s"], "Next compute h = 400 / 19.6.") == ["turn: nothing hidden or solved is shown"]


def test_one_echo_does_not_excuse_a_second_mention():
    wrote = ["so h = 400 / 19.6"]
    said = 'You wrote "h = 400 / 19.6". Now finish it: the answer is 20.4 m.'
    assert _leak_check(wrote, said) == ["turn: nothing hidden or solved is shown"]


def test_hidden_fields_are_never_excused_and_the_diagnosis_quotes_are_skipped():
    assert _leak_check(["hidden"], "hi", hidden_rubric=["x"]) == ["turn: nothing hidden or solved is shown"]
    run = load_script().Run("http://unused", shape_only=False)
    run.no_leaks("turn", {"message": "ok", "diagnosis": {"steps": [{"quote": "h = 400 / 19.6 = 20.4 m"}]}})
    assert run.failures == []


def test_quotes_and_accents_in_the_tutor_text_do_not_hide_an_echo():
    # The reply is compared unescaped: a JSON-escaped quote in front of the marker must not break the match
    wrote = ["h = 400 / 19.6"]
    assert _leak_check(wrote, "Look at “h = 400 / 19.6” again, είναι σωστό;") == []


def test_the_story_resets_what_the_student_wrote_between_learners(serve_tutor, capsys):
    # Maria's earlier words must not excuse something said to Nikos: both stories pass and neither leaks
    url = serve_tutor(ScriptedTutor())
    assert load_script().main(["--base-url", url]) == 0, capsys.readouterr().out
