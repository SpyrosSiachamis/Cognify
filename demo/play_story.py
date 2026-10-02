#!/usr/bin/env python3
"""Plays the Maria and Nikos story (docs/DEMO.md) against a running backend and checks every step.

    python demo/play_story.py                       # both learners against localhost:8000
    python demo/play_story.py --student maria
    python demo/play_story.py --shape-only          # real model: check rules and consistency, not exact wording

Standard library only, so it runs anywhere. It PLAYS REAL SESSIONS: Maria and Nikos end up with
one more verified run in the history. Restart the backend afterwards to reset the seeded demo
(the in-memory store reloads the seed at startup). It refuses non-local addresses unless you
pass --allow-remote, so the public demo is never changed by accident.

With --shape-only (the real model writes its own follow-up, so the canned answer is not a real solution)
either verdict is fine. The script then checks that everything agrees with the verdict it got: counts, concept
state, the two views, and whether the session is over. A 503 that says retryable is retried with the same
text, like the frontend's "Try again", and the hint count must not grow because of it.

Exit code 0 when every check passed, 1 otherwise (2: wrong address or backend unreachable). Experiments
(--force_experiment) are only reported: the stub tutor does not run them.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

MARIA = "16e82ef2-adee-4671-8393-c6b50ac91672"
NIKOS = "00915798-79f9-4362-84d0-839a0b3df9f2"
PROBLEM = (
    "A ball is thrown vertically upward with an initial velocity of 20 m/s. "
    "How high does it go before it starts to fall? (Use g = 9.8 m/s^2)"
)
SOLUTION_MARKERS = ("20.4 m", "400 / 19.6")  # the worked answer: never in a Master reply
HIDDEN_FIELDS = ("hidden", "rubric")
ECHO_CONTEXT = 4  # characters before a solution marker that must match what the student wrote ("h = ")
QUOTES = re.compile(r"[\"'`\u2018\u2019\u201c\u201d]")  # quoting someone does not change what they said

STORIES = {
    "maria": {
        "id": MARIA,
        "name": "Maria",
        "gap": "recognition",
        "method": "visual_decomposition",
        "turns": [
            "I found the time to the top, about 2.04 s, but I do not know how to get the height from the time.",
            "I drew it. At the top the speed is 0. I know u = 20 and g = 9.8, and I want the height.",
        ],
        "stress": "No time is given, so I use v^2 = u^2 - 2gh with v = 0 and u = 15: h = 225 / 19.6, about 11.5 m.",
        "follow_up_word": "balcony",
    },
    "nikos": {
        "id": NIKOS,
        "name": "Nikos",
        "gap": "procedure",
        "method": "worked_example",
        "turns": [
            "I used v^2 = u^2 - 2gh but I got h = -20.4 m, I think I got the sign wrong.",
            "The acceleration is -9.8 and v = 0, so h = 400 / 19.6.",
        ],
        "stress": "Downward is positive: v^2 = 5^2 + 2(9.8)(30) = 613, so v is about 24.8 m/s.",
        "follow_up_word": "downward",
    },
}


class Run:
    def __init__(self, base: str, shape_only: bool) -> None:
        self.base = base.rstrip("/")
        self.shape_only = shape_only
        self.failures: list[str] = []
        self.checks = 0
        self.written: list[str] = []  # what the student wrote in the story being played

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + path, data=data, method=method, headers={"content-type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"{}")

    def attempt(self, sid: str, text: str, tries: int = 4) -> tuple[int, dict, int]:
        """Send an attempt. A retryable 503 is sent again with the same text. Returns (status, body, retries)."""
        self.written.append(text)
        for retry in range(tries):
            status, body = self.call("POST", f"/api/session/{sid}/attempt", {"text": text})
            error = body.get("error", {}) if isinstance(body, dict) else {}
            if status != 503 or not error.get("retryable") or retry == tries - 1:
                return status, body, retry
            print(f"  ....  the backend said {error.get('code')} (retryable), trying again with the same answer")
            time.sleep(1)
        raise AssertionError("unreachable")

    def check(self, name: str, ok: bool, detail: object = "", strict_only: bool = False) -> bool:
        if strict_only and self.shape_only:
            return True
        self.checks += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok or detail == "" else f"  -> {detail}"))
        if not ok:
            self.failures.append(name)
        return ok

    def no_leaks(self, name: str, payload: dict) -> None:
        """Nothing hidden or solved in what the tutor wrote. The diagnosis is skipped (its quotes are the student's
        own words), and a marker the tutor only repeats from the student's own message is not a leak: Nikos writes
        "h = 400 / 19.6" himself, and "Not yet: 'h = 400 / 19.6' does not hold up" quotes him."""
        shown = {k: v for k, v in payload.items() if k != "diagnosis"}
        plain = QUOTES.sub("", "\n".join(_strings(shown)))
        written = QUOTES.sub("", "\n".join(self.written))
        leaked = [m for m in HIDDEN_FIELDS if m in json.dumps(shown)]
        leaked += [m for m in SOLUTION_MARKERS if m in plain and not _only_echoes(plain, m, written)]
        self.check(f"{name}: nothing hidden or solved is shown", not leaked, leaked)


def _strings(value: object) -> list[str]:
    """Every string inside a JSON value, unescaped (so quotes and accents compare with the student's text)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _strings(v)]
    if isinstance(value, list):
        return [t for v in value for t in _strings(v)]
    return []


def _only_echoes(shown: str, marker: str, written: str) -> bool:
    """True when every place `marker` appears in `shown` repeats the student's own words: the few characters in
    front of it, plus the marker, appear together in what the student wrote. "the height is 20.4 m" is not an echo
    of "I got h = -20.4 m"; "h = -20.4 m" is."""
    start = 0
    while (i := shown.find(marker, start)) != -1:
        before = shown[max(0, i - ECHO_CONTEXT):i]
        if before + marker not in written:
            return False
        start = i + len(marker)
    return True


def strategy_row(run: Run, student: str, gap: str, method: str) -> dict:
    _, view = run.call("GET", f"/api/strategies/{student}")
    return next((r for r in view["rows"] if r["gap"] == gap and r["method"] == method), {"uses": 0, "independent_successes": 0})


def play(run: Run, story: dict) -> str | None:
    name, student = story["name"], story["id"]
    run.written = []
    print(f"\n== {name} ==")
    before = strategy_row(run, student, story["gap"], story["method"])
    _, learner = run.call("GET", f"/api/learner/{student}")
    run.check("learner view is labelled seeded", learner.get("is_seeded") is True, learner.get("is_seeded"))

    status, start = run.call("POST", "/api/session", {"problem": PROBLEM, "subject": "physics", "student_id": student})
    if not run.check("session starts", status == 200, (status, start)):
        return None
    sid = start["session_id"]
    run.check("asks for a first thought, no help yet", start["phase"] == "ask_first_thought" and start["hints_used"] == 0, start)
    run.check("the question is the first-thought prompt", "try first" in start["message"].lower(), start["message"], True)

    status, turn, _ = run.attempt(sid, story["turns"][0])
    run.check("first thought gets a teaching turn", status == 200 and turn.get("phase") == "teach", (status, turn))
    run.no_leaks("teaching turn", turn)
    diagnosis, method = turn.get("diagnosis") or {}, turn.get("method") or {}
    run.check("diagnosis quotes the student's own words", any(s.get("quote") for s in diagnosis.get("steps", [])), diagnosis)
    run.check(f"main gap is {story['gap']}", diagnosis.get("main_gap") == story["gap"], diagnosis.get("main_gap"), True)
    run.check(f"method is {story['method']}", method.get("name") == story["method"], method, True)
    run.check("the method comes with an observed-history reason", bool(re.search(r"\d+ of \d+", method.get("reason", ""))), method, True)
    run.check("the reply was checked and approved", (turn.get("reply_check") or {}).get("approved") is True, turn.get("reply_check"))
    run.check("no hint used yet", turn.get("hints_used") == 0, turn.get("hints_used"), True)

    follow_up = None
    # The stub needs one more reply; the real model may need up to the backend's cap of teaching turns.
    for text in [*story["turns"][1:], *[story["turns"][-1]] * 4]:
        hints_before = turn.get("hints_used", 0)
        status, turn, retried = run.attempt(sid, text)
        run.check("student reply is accepted", status == 200, (status, turn))
        if status != 200:
            return None
        run.no_leaks("next turn", turn)
        if retried:  # the failed request must not have cost the student a hint
            run.check("a retried request did not cost an extra hint", turn.get("hints_used", 0) <= hints_before + 1,
                      (hints_before, turn.get("hints_used")))
        if turn.get("phase") == "stress_test":
            follow_up = turn["follow_up"]["problem"]
            break
    appeared = run.check("support is removed: the stress test appears", follow_up is not None, turn)
    if follow_up is None or not appeared:
        return None
    run.check("the follow-up is a different problem", follow_up != PROBLEM, follow_up)
    run.check(f"the follow-up fits {name}'s gap", story["follow_up_word"] in follow_up.lower(), follow_up, True)
    run.check("the stress test shows only the problem", set(turn["follow_up"]) == {"problem"}, turn["follow_up"])
    run.check("one hint was needed", turn["hints_used"] == 1, turn["hints_used"], True)

    status, verdict, _ = run.attempt(sid, story["stress"])
    run.check("the answer gets a verdict", status == 200 and verdict.get("phase") == "verdict", (status, verdict))
    result = verdict.get("verdict") or {}
    run.check("VERIFIED, decided by code", result.get("result") == "VERIFIED", result.get("result"), True)
    verified = result.get("result") == "VERIFIED"
    run.check(
        "VERIFIED means independent, and the session ends",
        not verified or (result.get("independent") is True and verdict.get("session_over") is True),
        verdict,
    )
    changes = result.get("changes") or {}
    strategy = changes.get("strategy") or {}
    over = verdict.get("session_over") is True

    if run.shape_only:
        print(f"  info  verdict: {result.get('result')}, session {'over' if over else 'continues'}")
        run.check("the verdict is VERIFIED or NOT YET", result.get("result") in ("VERIFIED", "NOT YET"), result.get("result"))
        concept_after = (changes.get("concept") or {}).get("after")
        run.check("the concept is verified exactly when the answer was VERIFIED", (concept_after == "verified") == verified, changes.get("concept"))
        run.check("a NOT YET names what is still missing", verified or bool(result.get("remaining_gap")) or not strategy, result)
        if strategy:
            gap, method = strategy.get("gap", ""), strategy.get("method", "")
            b_, a_ = strategy.get("before", {}), strategy.get("after", {})
            run.check(
                "strategy counts moved by one use, and one success only if VERIFIED",
                a_.get("uses") == b_.get("uses", 0) + 1 and a_.get("independent_successes") == b_.get("independent_successes", 0) + int(verified),
                (b_, a_),
            )
            row = strategy_row(run, student, gap, method)
            run.check("How You Learn shows the same counts as the verdict",
                      (row["uses"], row["independent_successes"]) == (a_.get("uses"), a_.get("independent_successes")), (row, a_))
        else:
            print("  info  no teaching method was used, so no strategy counts changed")
        _, learner = run.call("GET", f"/api/learner/{student}")
        states = [c["state"] for c in learner["concepts"]]
        run.check("Understanding Map shows verified after a VERIFIED answer", not verified or "verified" in states, states)
        status, after_turn = run.call("POST", f"/api/session/{sid}/attempt", {"text": "one more"})
        if over:
            run.check("a finished session refuses more turns", status == 409 and after_turn.get("error", {}).get("code") == "session_over", (status, after_turn))
        else:
            run.check("after a first NOT YET the student goes back to teaching", status in (200, 503) and (status == 503 or after_turn.get("phase") == "teach"), (status, after_turn.get("phase")))
            run.call("POST", f"/api/session/{sid}/exit")  # leave nothing open
        return follow_up

    run.check("the concept moves to verified", (changes.get("concept") or {}).get("after") == "verified", changes.get("concept"))
    run.check(
        "strategy counts tick up by one use and one success",
        strategy.get("after") == {"uses": before["uses"] + 1, "independent_successes": before["independent_successes"] + 1},
        (before, strategy.get("after")),
    )
    after = strategy_row(run, student, story["gap"], story["method"])
    run.check("How You Learn shows the same new counts", after["uses"] == before["uses"] + 1, after)
    _, learner = run.call("GET", f"/api/learner/{student}")
    run.check("Understanding Map shows verified", any(c["state"] == "verified" for c in learner["concepts"]), learner["concepts"])

    status, err = run.call("POST", f"/api/session/{sid}/attempt", {"text": "one more"})
    run.check("a finished session refuses more turns", status == 409 and err.get("error", {}).get("code") == "session_over", (status, err))
    return follow_up


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--student", choices=["maria", "nikos", "both"], default="both")
    parser.add_argument("--shape-only", action="store_true", help="skip exact wording checks (real model)")
    parser.add_argument("--allow-remote", action="store_true", help="allow a non-local address")
    args = parser.parse_args(argv)

    host = urlparse(args.base_url).hostname
    if host not in ("localhost", "127.0.0.1", "::1") and not args.allow_remote:
        print(f"Refusing to play sessions against {args.base_url}: it changes the demo history. Use --allow-remote.")
        return 2

    run = Run(args.base_url, args.shape_only)
    print(f"Playing against {run.base} ({'shape only' if run.shape_only else 'exact story'})")
    try:
        status, body = run.call("GET", "/api/health")
    except OSError as err:
        print(f"Cannot reach the backend: {err}")
        return 2
    run.check("health", status == 200 and body == {"status": "ok"}, body)

    follow_ups = {}
    for key in (["maria", "nikos"] if args.student == "both" else [args.student]):
        follow_ups[key] = play(run, STORIES[key])
    if len(follow_ups) == 2 and all(follow_ups.values()):
        print("\n== Same problem, two learners ==")
        run.check("the two students got different follow-ups", follow_ups["maria"] != follow_ups["nikos"], follow_ups)

    status, forced = run.call("POST", "/api/session", {"problem": PROBLEM, "student_id": MARIA, "force_experiment": True})
    print("\n== Experiment flag ==")
    run.check("force_experiment is accepted", status == 200, (status, forced))
    if status == 200:
        _, turn = run.call("POST", f"/api/session/{forced['session_id']}/attempt", {"text": STORIES["maria"]["turns"][0]})
        if (turn.get("method") or {}).get("experiment"):
            run.check("an experiment is labelled on screen", "different" in turn["method"]["reason"].lower(), turn["method"])
        else:
            print("  SKIP  this backend ran no experiment (the stub tutor ignores the flag)")
        run.call("POST", f"/api/session/{forced['session_id']}/exit")

    print(f"\n{run.checks - len(run.failures)}/{run.checks} checks passed")
    if run.failures:
        print("Failed:\n  " + "\n  ".join(run.failures))
        return 1
    if run.shape_only:
        print("Every check agrees with the verdicts above. Restart the backend to reset the seeded demo history.")
    else:
        print("The Maria story runs end to end. Restart the backend to reset the seeded demo history.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
