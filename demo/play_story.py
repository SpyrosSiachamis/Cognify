#!/usr/bin/env python3
"""Plays the Maria and Nikos story (docs/DEMO.md) against a running backend and checks every step.

    python demo/play_story.py                       # both learners against localhost:8000
    python demo/play_story.py --student maria
    python demo/play_story.py --shape-only          # real model: check shapes and rules, not exact wording

Standard library only, so it runs anywhere. It PLAYS REAL SESSIONS: Maria and Nikos end up with
one more verified run in the history. Restart the backend afterwards to reset the seeded demo
(the in-memory store reloads the seed at startup). It refuses non-local addresses unless you
pass --allow-remote, so the public demo is never changed by accident.

Exit code 0 when every check passed, 1 otherwise. Experiments (--force_experiment) are only
reported: the stub tutor does not run them.
"""

import argparse
import json
import re
import sys
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

    def check(self, name: str, ok: bool, detail: object = "", strict_only: bool = False) -> bool:
        if strict_only and self.shape_only:
            return True
        self.checks += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok or detail == "" else f"  -> {detail}"))
        if not ok:
            self.failures.append(name)
        return ok

    def no_leaks(self, name: str, payload: dict) -> None:
        # What the tutor wrote. A quote is the student's own words (Nikos writes -20.4 m himself).
        shown = {k: v for k, v in payload.items() if k != "diagnosis"}
        text = json.dumps(shown)
        leaked = [m for m in (*SOLUTION_MARKERS, *HIDDEN_FIELDS) if m in text]
        self.check(f"{name}: nothing hidden or solved is shown", not leaked, leaked)


def strategy_row(run: Run, student: str, gap: str, method: str) -> dict:
    _, view = run.call("GET", f"/api/strategies/{student}")
    return next((r for r in view["rows"] if r["gap"] == gap and r["method"] == method), {"uses": 0, "independent_successes": 0})


def play(run: Run, story: dict) -> str | None:
    name, student = story["name"], story["id"]
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

    status, turn = run.call("POST", f"/api/session/{sid}/attempt", {"text": story["turns"][0]})
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
    for text in story["turns"][1:]:
        status, turn = run.call("POST", f"/api/session/{sid}/attempt", {"text": text})
        run.check("student reply is accepted", status == 200, (status, turn))
        run.no_leaks("next turn", turn)
        if turn.get("phase") == "stress_test":
            follow_up = turn["follow_up"]["problem"]
            break
    if follow_up is None:  # the real model may need more teaching turns
        for _ in range(4):
            status, turn = run.call("POST", f"/api/session/{sid}/attempt", {"text": story["turns"][-1]})
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

    status, verdict = run.call("POST", f"/api/session/{sid}/attempt", {"text": story["stress"]})
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
    run.check("the concept moves to verified", (changes.get("concept") or {}).get("after") == "verified", changes.get("concept"))
    strategy = changes.get("strategy") or {}
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
    print("The Maria story runs end to end. Restart the backend to reset the seeded demo history.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
