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

    monkeypatch.setattr(SessionService, "__init__", broken_init)
    url = serve_tutor(ScriptedTutor(fail_once={"follow_up"}))
    code = load_script().main(["--base-url", url, "--shape-only", "--student", "maria"])
    out = capsys.readouterr().out
    assert code == 1 and "FAIL  a retried request did not cost an extra hint" in out, out
