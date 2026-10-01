"""The tutor outside the seeded ball problem: it must reason from the actual problem, not assume kinematics.

    docker compose exec backend python -m pytest -m live tests/tutor/test_general_live.py -v -s
"""

import asyncio
import os
import re

import pytest

from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest, VerdictTurn
from app.tutor.agent import AgentTutor
from app.tutor.follow_up import overlap
from app.tutor.language import student_language, written_in
from app.user.service import SessionService

from .conftest import teach_request

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("TUTOR_MODEL_ID"), reason="set TUTOR_MODEL_ID to a Bedrock model ID"),
]

ALGEBRA = "Solve for x: 3x + 5 = 20."
CAR = "A car starts from rest and accelerates at 2 m/s^2 for 5 s. How far does it travel in that time?"
DECIMALS = "Which number is bigger, 0.5 or 0.45? Explain why."


def teach(store, problem: str, text: str, **update):
    tutor = AgentTutor(store)
    setup = asyncio.run(tutor.set_up(problem, None))
    print("SET UP:", setup.model_dump_json())
    result, trace = asyncio.run(tutor.teach_with_trace(
        teach_request(text, problem=problem, solution=setup.solution, concept_name=setup.concept_name, **update)))
    print(trace.model_dump_json(indent=2))
    print("TO STUDENT:", result.output.reply)
    assert written_in(result.output.reply, student_language(text))
    return setup, result, trace


def statuses(result):
    return {s.role: s.status for s in result.output.steps}


def test_algebra_set_up_is_not_kinematics(store):
    tutor = AgentTutor(store)
    setup = asyncio.run(tutor.set_up(ALGEBRA, "math"))
    assert re.search(r"\b5\b", setup.solution.result)
    assert "kinematic" not in setup.concept_name.lower()


def test_algebra_partial_reasoning(store):
    setup, result, trace = teach(store, ALGEBRA, "I subtracted 5 from both sides and got 3x = 15, but I'm not sure what to do next.")
    assert any(s.status == "correct" and "15" in (s.quote or "") for s in result.output.steps)
    assert result.output.main_gap is not None and trace.mode == "teach"
    assert not re.search(r"x\s*=\s*5\b", result.output.reply)


def test_algebra_good_method_arithmetic_slip(store):
    setup, result, trace = teach(store, ALGEBRA, "First I take 5 away from both sides: 3x = 25. Then x = 25 / 3.")
    assert any(s.status == "wrong" and "25" in (s.quote or "") for s in result.output.steps)
    assert result.output.main_gap == "procedure"
    assert result.output.error is not None


def test_other_kinematics_problem_wrong_method(store):
    setup, result, trace = teach(store, CAR, "Its speed after 5 s is 2 x 5 = 10 m/s, so it goes 10 x 5 = 50 m.")
    assert any(s.status == "correct" and "10 m/s" in (s.quote or "") for s in result.output.steps)
    assert any(s.status == "wrong" and "50" in (s.quote or "") for s in result.output.steps)
    assert result.output.error is not None
    assert "25" not in result.output.reply  # the answer (25 m) is not given away


def test_correct_answer_wrong_explanation(store):
    setup, result, trace = teach(store, DECIMALS, "0.5 is bigger, because it has fewer digits after the point.")
    assert "wrong" in statuses(result).values(), "a wrong explanation must not pass because the answer is right"
    assert result.output.main_gap == "concept"


@pytest.mark.parametrize("text", ["I don't know.", "δεν ξέρω"])
def test_no_reasoning_is_a_probe_in_the_students_language(store, text):
    setup, result, trace = teach(store, ALGEBRA, text)
    assert trace.mode == "probe" and result.output.evidence == "insufficient" and result.method is None


def test_transfer_session_on_algebra(store):
    """Right from the start: straight to a fresh problem, which must be new, then judged."""
    svc = SessionService(AgentTutor(store), store)
    start = asyncio.run(svc.start(SessionStartRequest(problem=ALGEBRA, student_id=MARIA_ID)))
    turn = asyncio.run(svc.attempt(start.session_id, "Subtract 5 from both sides: 3x = 15. Divide by 3: x = 5."))
    print(turn.model_dump_json(indent=2))
    assert turn.phase == "stress_test" and turn.follow_up is not None
    fresh = turn.follow_up.problem
    assert overlap(fresh, ALGEBRA) < 0.6 and "3x + 5 = 20" not in fresh.replace(" ", " ")
    assert not re.search(r"(hint|remember|use the formula)", fresh, re.I)
    verdict = asyncio.run(svc.attempt(start.session_id, "I don't know."))
    print(verdict.model_dump_json(indent=2))
    assert isinstance(verdict, VerdictTurn) and verdict.verdict.result == "NOT YET"


# ---- diagnosis generalization: correct work gets no invented gap; real problems still get one ----

SOLVED_NO_GAP = [
    (ALGEBRA, "Subtract 5 from both sides: 3x = 15. Divide both sides by 3: x = 5."),  # complete
    (ALGEBRA, "x = (20 - 5) / 3 = 5"),  # concise
    (CAR, "Its average speed is (0 + 10) / 2 = 5 m/s, so in 5 s it goes 5 x 5 = 25 m."),  # equivalent method
]


@pytest.mark.parametrize(("problem", "text"), SOLVED_NO_GAP, ids=["complete", "concise", "equivalent-method"])
def test_correct_work_gets_no_invented_gap(store, problem, text):
    setup, result, trace = teach(store, problem, text)
    assert result.output.main_gap is None, f"invented gap: {result.output.main_gap}"
    assert not any(s.status in ("wrong", "missing") for s in result.output.steps)
    assert trace.mode == "acknowledge" and result.method is None


HAS_GAP = [
    (ALGEBRA, "x = 5, because 20 divided by 5 is 4 and 4 plus 1 is 5."),  # right answer, wrong reasoning
    (CAR, "Its final speed is 2 x 5 = 10 m/s."),  # stops before the distance
    (CAR, "Distance is acceleration times time, so 2 x 5 = 10 m."),  # conceptual error
]


@pytest.mark.parametrize(("problem", "text"), HAS_GAP, ids=["right-answer-wrong-reason", "incomplete", "conceptual-error"])
def test_real_problems_still_get_a_diagnosis(store, problem, text):
    setup, result, trace = teach(store, problem, text)
    assert result.output.main_gap is not None
    assert trace.mode == "teach"
    if any(s.status == "wrong" for s in result.output.steps):
        assert result.output.error is not None, "a wrong step comes with its stated error"


# ---- unfinished is not wrong: correct intermediate work that stops before the next operation ----

STOPS_AFTER_CORRECT_WORK = [
    ("Given matrix A = [[2, 1], [-1, 3]] and vector x = [4, 2], calculate A × x.",
     "I multiplied each row of A by x entry by entry and got [8, 2] and [-4, 6]. "
     "I don't know how to turn those into a single vector.", "[8, 2]"),
    ("Find the mean of 4, 8 and 9.", "I added 4, 8 and 9 and got 21, but I'm not sure what to do next.", "21"),
    ("Work out 1/3 + 1/4.", "I rewrote them as 4/12 and 3/12, but I don't know how to finish.", "4/12"),
    (CAR, "Its final speed is 2 x 5 = 10 m/s, so its average speed is 5 m/s. I'm stuck on the distance.", "5 m/s"),
]


@pytest.mark.parametrize(("problem", "text", "done"), STOPS_AFTER_CORRECT_WORK,
                         ids=["matrix", "mean", "fractions", "kinematics"])
def test_correct_work_that_stops_is_unfinished_not_wrong(store, problem, text, done):
    setup, result, trace = teach(store, problem, text)
    steps = result.output.steps
    assert any(s.status == "correct" and done in (s.quote or "") for s in steps), "the correct work done is credited"
    assert not any(s.status == "wrong" for s in steps), "unfinished work is not wrong"
    assert result.output.error is None
    assert any(s.status == "missing" for s in steps) and trace.mode == "teach"
    assert result.output.main_gap not in (None, "concept"), "stopping is not a misconception"
