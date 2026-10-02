"""CORS_ORIGINS: which frontend addresses the browser may call the API from."""

import subprocess
import urllib.error
import urllib.request

import pytest

from app.main import DEFAULT_CORS_ORIGINS, cors_origins
from tests.user.test_demo_mode import _clean_env, _serve, _wait_until_up


def test_the_local_frontend_is_allowed_by_default_on_both_spellings():
    assert cors_origins({}) == ["http://localhost:3000", "http://127.0.0.1:3000"]
    assert cors_origins({"CORS_ORIGINS": ""}) == list(DEFAULT_CORS_ORIGINS)
    assert cors_origins({"CORS_ORIGINS": "   "}) == list(DEFAULT_CORS_ORIGINS)  # an empty value in .env is "unset"


def test_a_setting_replaces_the_defaults_and_is_tidied():
    assert cors_origins({"CORS_ORIGINS": "https://cognify.example.com"}) == ["https://cognify.example.com"]
    assert cors_origins({"CORS_ORIGINS": " https://a.example.com/ , http://localhost:3000,https://a.example.com "}) == [
        "https://a.example.com",
        "http://localhost:3000",
    ]


@pytest.mark.parametrize(
    "bad",
    ["*", "https://a.com,*", "localhost:3000", "a.example.com", "http://a.com/app", "ftp://a.com",
     "https://a b.com", "http://a.com,,http://b.com", "http://a.com;http://b.com"],
)
def test_a_wildcard_or_malformed_entry_stops_the_start(bad):
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        cors_origins({"CORS_ORIGINS": bad})


def _preflight(url: str, origin: str) -> dict[str, str]:
    request = urllib.request.Request(
        url + "/api/session", method="OPTIONS",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as err:  # a refused preflight answers 400
        return {"status": str(err.code), **{k.lower(): v for k, v in err.headers.items()}}


def _serving(**env: str):
    proc, url = _serve(_clean_env(**env))
    assert _wait_until_up(proc, url), "the server did not start"
    return proc, url


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    proc.wait(timeout=15)


def test_a_browser_on_the_listed_frontend_is_let_in_and_others_are_not():
    proc, url = _serving(CORS_ORIGINS="https://cognify.example.com,http://localhost:3000")
    try:
        allowed = _preflight(url, "https://cognify.example.com")
        assert allowed.get("access-control-allow-origin") == "https://cognify.example.com"
        assert _preflight(url, "http://localhost:3000").get("access-control-allow-origin") == "http://localhost:3000"
        for stranger in ("https://evil.example.com", "http://cognify.example.com", "https://cognify.example.com.evil.com"):
            refused = _preflight(url, stranger)
            assert "access-control-allow-origin" not in refused, stranger
    finally:
        _stop(proc)


def test_the_defaults_let_the_local_frontend_in_on_localhost_and_127_0_0_1_only():
    proc, url = _serving()
    try:
        for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            assert _preflight(url, origin).get("access-control-allow-origin") == origin
        for other in ("http://localhost:3001", "https://cognify.example.com"):
            assert "access-control-allow-origin" not in _preflight(url, other)
    finally:
        _stop(proc)


def test_a_real_request_from_an_allowed_origin_carries_the_header():
    proc, url = _serving(CORS_ORIGINS="https://cognify.example.com")
    try:
        request = urllib.request.Request(url + "/api/health", headers={"Origin": "https://cognify.example.com"})
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.headers["access-control-allow-origin"] == "https://cognify.example.com"
    finally:
        _stop(proc)


@pytest.mark.parametrize("bad", ["*", "localhost:3000"])
def test_the_server_refuses_to_start_with_a_bad_setting(bad):
    proc, _ = _serve(_clean_env(CORS_ORIGINS=bad))
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("the server started with an invalid CORS_ORIGINS")
    assert proc.returncode != 0 and "CORS_ORIGINS" in (proc.stdout.read() if proc.stdout else "")


def test_a_wildcard_gets_its_own_clear_message():
    with pytest.raises(RuntimeError, match=r"must not be '\*'"):
        cors_origins({"CORS_ORIGINS": "*"})
    with pytest.raises(RuntimeError, match="not an origin"):
        cors_origins({"CORS_ORIGINS": "localhost:3000"})
