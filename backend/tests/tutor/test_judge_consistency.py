"""A fresh-problem answer whose own work is complete and consistent is not called incorrect because the generated
rubric disagrees.

From a live session (apples_fresh_case.json): the rubric split 276 kg in a 4:7 ratio as 100.8 kg (it is 100.36), the
student's work was right throughout, and the judge called it incorrect "due to rounding", so the student got
"Not yet. Here is what we will try differently." A false calculation or a value with no source still stays NOT YET.
"""

import json
from pathlib import Path

import pytest

from app.tutor.consistency import check_work
from app.session.schema import VerdictTurn

from .fakes import STUDENT_OK
from .test_transfer_regressions import SOLVED_AT_ONCE, rig, send

CASE = json.loads((Path(__file__).parent / "apples_fresh_case.json").read_text(encoding="utf-8"))
FRESH = {k: CASE[k] for k in ("problem", "concept_invariant", "target_gap", "target_step", "perturbation", "difficulty",
                              "hidden_rubric")}
ANSWER = CASE["answer"]
# What the live judge said about the exact answer.
JUDGE_SAYS_WRONG = {**STUDENT_OK, "correct": False, "note": (
    "Student's final result (140.45 kg and 160.64 kg) does not match the rubric's expected result (141 kg and "
    "160.2 kg) due to rounding errors in intermediate steps.")}
FALSE_ARITHMETIC = ANSWER.replace("125.4545 + 15 = 140.4545", "125.45 + 15 = 141")
CONTRADICTION = ANSWER.replace("Storage X has approximately 140.45 kg", "Storage X has 141 kg")
GENERIC_NOT_YET = "Not yet. Here is what we will try differently."


def judged(store, answer, judge=JUDGE_SAYS_WRONG):
    svc, sid, model, verifier = rig(store, [SOLVED_AT_ONCE], replies=["unused"], verifier_results=[],
                                    follow_ups=(FRESH,), student_checks=[judge])
    svc.tracing = True
    fresh = send(svc, sid, "36 - 12 = 24 and 24 ÷ 6 = 4, so 4 books.")
    assert fresh.phase == "stress_test" and fresh.follow_up.problem == FRESH["problem"]
    verdict = send(svc, sid, answer)
    assert isinstance(verdict, VerdictTurn)
    checks = [e.payload for e in store.list_trace_events(sid) if e.event_type == "JUDGE_CONSISTENCY_CHECK"]
    return verdict, checks


def test_the_exact_consistent_answer_is_verified_not_the_generic_not_yet(store):
    verdict, (check,) = judged(store, ANSWER)
    assert verdict.verdict.result == "VERIFIED" and verdict.message != GENERIC_NOT_YET
    assert "follows from the problem" in verdict.verdict.evidence
    assert (check.judge_correct, check.consistent, check.overridden) == (False, True, True)


def test_false_arithmetic_is_still_not_yet(store):
    verdict, (check,) = judged(store, FALSE_ARITHMETIC)
    assert verdict.verdict.result == "NOT YET" and verdict.message == GENERIC_NOT_YET
    assert not check.overridden and any("does not follow from its own calculation" in r for r in check.reasons)


def test_correct_work_then_a_contradicting_final_answer_is_still_not_yet(store):
    verdict, (check,) = judged(store, CONTRADICTION)
    assert verdict.verdict.result == "NOT YET"
    assert not check.overridden and any("141 has no source" in r for r in check.reasons)


def test_a_correct_verdict_is_left_alone(store):
    verdict, checks = judged(store, ANSWER, judge=STUDENT_OK)
    assert verdict.verdict.result == "VERIFIED" and checks == []  # the check only runs on an "incorrect"


@pytest.mark.parametrize("answer, consistent", [
    (ANSWER, True),
    (FALSE_ARITHMETIC, False),
    (CONTRADICTION, False),
    (ANSWER + "\nSo Storage X actually has 150 kg.", False),  # a stated value nothing derives
    ("Storage X has 140.45 kg and Storage Y has 160.64 kg.", False),  # an answer with no work
    ("8% of 300 = 30 kg spoiled, so 270 kg remain.", False),  # a false percentage
])
def test_the_consistency_check(answer, consistent):
    assert check_work(answer, FRESH["problem"]).consistent is consistent
