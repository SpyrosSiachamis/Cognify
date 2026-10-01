"""demo/play_story.py against the real app on a real port, so the rehearsal script cannot rot."""

import importlib.util
import os
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app.main import app

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


@pytest.fixture
def live_url():
    app.dependency_overrides.clear()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "the test server did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


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
