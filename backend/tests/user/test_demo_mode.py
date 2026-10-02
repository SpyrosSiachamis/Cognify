"""DEMO_MODE=offline (F27): the saved story with no network, no credentials and no model."""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from app.main import check_tutor_config, tutor_mode

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND.parent / "demo" / "play_story.py"

# A real tutor that cannot work: a model is named, but there is no region and no credentials
BROKEN_REAL_TUTOR = {"TUTOR_MODEL_ID": "some.model"}


def test_which_tutor_serves_the_api():
    assert tutor_mode({}) == "stub"
    assert tutor_mode({"TUTOR_MODEL_ID": "m"}) == "agent"
    assert tutor_mode({"DEMO_MODE": "offline"}) == "offline"
    assert tutor_mode({"DEMO_MODE": " OFFLINE "}) == "offline"
    assert tutor_mode({"DEMO_MODE": "offline", "TUTOR_MODEL_ID": "m"}) == "offline"  # the switch wins
    assert tutor_mode({"DEMO_MODE": "off", "TUTOR_MODEL_ID": "m"}) == "agent"
    assert tutor_mode({"DEMO_MODE": "", "TUTOR_MODEL_ID": "m"}) == "agent"  # an empty value in .env is "unset"


@pytest.mark.parametrize("typo", ["ofline", "on", "true", "1", "offlinex"])
def test_a_mistyped_value_stops_the_start_instead_of_running_the_real_tutor(typo):
    with pytest.raises(RuntimeError, match="DEMO_MODE"):
        tutor_mode({"DEMO_MODE": typo, "TUTOR_MODEL_ID": "m"})


def test_offline_skips_the_ai_configuration_check(monkeypatch):
    for name in ("AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_BEARER_TOKEN_BEDROCK"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TUTOR_MODEL_ID", "some.model")
    monkeypatch.setenv("DEMO_MODE", "offline")
    assert check_tutor_config() == "offline"  # does not raise
    monkeypatch.delenv("DEMO_MODE")
    with pytest.raises(RuntimeError, match="DEMO_MODE=offline"):  # the error now names the way out
        check_tutor_config()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "TUTOR_", "DEMO_"))}
    env.update(PYTHONPATH=str(BACKEND), AUTOSEED="true", PYDANTIC_AI_NO_BANNER="1", AWS_EC2_METADATA_DISABLED="true")
    env.update(extra)
    return env


def _serve(env: dict[str, str]) -> tuple[subprocess.Popen, str]:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return proc, f"http://127.0.0.1:{port}"


def _wait_until_up(proc: subprocess.Popen, url: str, seconds: float = 20) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline and proc.poll() is None:
        try:
            urllib.request.urlopen(url + "/api/health", timeout=1).read()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def test_the_whole_story_plays_offline_even_with_a_broken_real_tutor_configured():
    proc, url = _serve(_clean_env(DEMO_MODE="offline", **BROKEN_REAL_TUTOR))
    try:
        assert _wait_until_up(proc, url), "the server did not start with DEMO_MODE=offline"
        played = subprocess.run([sys.executable, str(SCRIPT), "--base-url", url], capture_output=True, text=True, timeout=120)
        assert played.returncode == 0, played.stdout[-1500:]
        assert "checks passed" in played.stdout and "FAIL" not in played.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=15)


def test_without_the_switch_the_same_configuration_refuses_to_start():
    proc, url = _serve(_clean_env(**BROKEN_REAL_TUTOR))
    try:
        proc.wait(timeout=30)  # uvicorn exits when the lifespan check raises
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("the server started with a real tutor that cannot work")
    output = proc.stdout.read() if proc.stdout else ""
    assert proc.returncode != 0 and "DEMO_MODE=offline" in output


def test_a_typo_stops_the_server_before_it_serves_anything():
    proc, url = _serve(_clean_env(DEMO_MODE="ofline"))
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("the server started with an invalid DEMO_MODE")
    assert proc.returncode != 0
    assert "DEMO_MODE" in (proc.stdout.read() if proc.stdout else "")
