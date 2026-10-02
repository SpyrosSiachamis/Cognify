"""A generated expected solution is checked by code before anything is judged against it (expected_check.py).

From a live session (1debff9e): the fresh problem asked for a 120 m² flower bed whose length is 4 m less than twice
its width, and the follow-up model's rubric answered "8 m × 12 m" (96 m²). The judge marked a student who solved it
correctly (w = 1 + √61 ≈ 8.81 m) as incorrect against that rubric: "Not yet. Here is what we will try differently."
"""

import asyncio

import pytest

from app.user.errors import ApiError
from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest
from app.tutor.agent import AgentTutor
from app.tutor.expected_check import ExpectedCheck, check_expected
from app.tutor.follow_up import FollowUpInput, FollowUpUnavailable, write_follow_up
from app.user.service import SessionService

from .fakes import FOLLOW_UP, FOLLOW_UP_OK, SETUP, FakeVerifier, ScriptedModel, diagnosis

BED = ("A gardener wants to design a rectangular flower bed with an area of 120 square meters. The length of the "
       "flower bed must be 4 meters less than twice its width. What are the dimensions of the flower bed?")
BED_CONDITIONS = ["l = 2*w - 4", "w*l = 120"]
RIGHT = ExpectedCheck(values={"w": "1 + sqrt(61)", "l": "2*w - 4"}, conditions=BED_CONDITIONS)
RIGHT_ANSWER = "Width = 1 + √61 ≈ 8.81 m, length = 2√61 - 2 ≈ 13.62 m."
LIVE_WRONG = ExpectedCheck(values={"w": "8", "l": "12"}, conditions=BED_CONDITIONS)
LIVE_WRONG_ANSWER = "Solves the equation to find the valid width and computes the length. The dimensions are 8 m × 12 m."
RECTANGLE = "A rectangle has an area of 48 m². Its length is 2 m greater than its width. Find its dimensions."


def status(candidate, problem=BED, answer=RIGHT_ANSWER):
    return check_expected(candidate, problem, answer).status


# ---- the module ----


def test_a_correct_whole_number_solution_is_accepted():
    candidate = ExpectedCheck(values={"w": "6", "l": "w + 2"}, conditions=["l = w + 2", "w*l = 48"])
    assert status(candidate, RECTANGLE, "Width = 6 m, Length = 8 m") == "VALID"


def test_an_incorrect_expected_answer_is_rejected():
    candidate = ExpectedCheck(values={"w": "5", "l": "w + 2"}, conditions=["l = w + 2", "w*l = 48"])
    verdict = check_expected(candidate, RECTANGLE, "Width = 5 m, Length = 7 m")
    assert verdict.status == "INVALID_EXPECTED_SOLUTION" and "35" in verdict.reason  # 5 × 7 = 35, not 48


def test_the_live_flower_bed_rubric_8_by_12_is_rejected():
    verdict = check_expected(LIVE_WRONG, BED, LIVE_WRONG_ANSWER)
    assert verdict.status == "INVALID_EXPECTED_SOLUTION" and "96" in verdict.reason


def test_a_right_candidate_does_not_rescue_a_wrong_stated_answer():
    # Code verifies; it never swaps in the candidate's answer for the one the rubric states.
    assert status(RIGHT, answer=LIVE_WRONG_ANSWER) == "INVALID_EXPECTED_SOLUTION"


def test_the_irrational_solution_1_plus_sqrt_61_is_accepted():
    assert status(RIGHT) == "VALID"
    written = ExpectedCheck(values={"w": "1 + √61", "l": "2√61 - 2"}, conditions=["l = 2w - 4", "w(2w - 4) = 120"])
    assert status(written) == "VALID"  # √, implicit products and the rounded answer text are all read
    assert status(RIGHT, answer="Width = 8.8 m, length = 13.6 m") == "VALID"  # rounding to what the answer writes
    assert status(RIGHT, answer="Width = 8.9 m, length = 13.6 m") == "INVALID_EXPECTED_SOLUTION"


def test_a_percentage_is_read():
    problem = "A jacket costs $80 and is discounted by 25%. What is the new price?"
    candidate = ExpectedCheck(values={"p": "60"}, conditions=["p = 80 * (1 - 25%)"])
    assert status(candidate, problem, "$60") == "VALID"
    assert status(candidate.model_copy(update={"values": {"p": "64"}}), problem, "$64") == "INVALID_EXPECTED_SOLUTION"


@pytest.mark.parametrize("candidate", [
    None,  # the model gave none (a non-numeric problem)
    ExpectedCheck(values={"w": "solve(w)"}, conditions=["w*l = 120"]),  # something code cannot read
    ExpectedCheck(values={"w": "8", "l": "12"}, conditions=["w*l = 96"]),  # does not encode this problem's numbers
])
def test_what_code_cannot_verify_is_not_deterministically_verifiable(candidate):
    assert status(candidate, answer=LIVE_WRONG_ANSWER) == "NOT_DETERMINISTICALLY_VERIFIABLE"


# ---- the integration points ----

BED_SETUP_WRONG = {"concept_name": "Quadratic equations", "steps": ["w(2w - 4) = 120", "w = 8, l = 12"],
                   "result": "8 m × 12 m", "expected_check": LIVE_WRONG.model_dump()}
BED_SETUP_RIGHT = {"concept_name": "Quadratic equations", "steps": ["w(2w - 4) = 120", "w² - 2w - 60 = 0",
                   "w = 1 + √61 ≈ 8.81 m, l = 2√61 - 2 ≈ 13.62 m"], "result": "8.81 m × 13.62 m",
                   "expected_check": RIGHT.model_dump()}


def start(store, setups):
    model = ScriptedModel([diagnosis(("set_up", "correct", "w(2w - 4) = 120"))], setup=setups)
    svc = SessionService(AgentTutor(store, model.model, FakeVerifier().model), store)
    return model, svc, asyncio.run(svc.start(SessionStartRequest(problem=BED, student_id=MARIA_ID)))


def test_an_invalid_set_up_solution_is_regenerated_before_anything_uses_it(store):
    model, svc, started = start(store, [BED_SETUP_WRONG, BED_SETUP_RIGHT])
    assert len(model.setup_inputs) == 2  # the 8 × 12 solution went back to the model
    asyncio.run(svc.attempt(started.session_id, "Let w be the width, so w(2w - 4) = 120."))
    assert model.reasoning_inputs[0]["final_answer"] == "8.81 m × 13.62 m"  # diagnosis sees only the checked answer


def test_an_invalid_set_up_solution_that_persists_never_reaches_diagnosis(store):
    model = ScriptedModel([diagnosis(("set_up", "correct", "w(2w - 4) = 120"))], setup=[BED_SETUP_WRONG])
    svc = SessionService(AgentTutor(store, model.model, FakeVerifier().model), store)
    with pytest.raises(ApiError) as failed:
        asyncio.run(svc.start(SessionStartRequest(problem=BED, student_id=MARIA_ID)))
    assert failed.value.status == 503 and model.reasoning_calls == 0  # a retryable error, never a wrong answer


def test_a_set_up_without_a_candidate_keeps_the_existing_behaviour(store):
    model, _, started = start(store, [SETUP])  # the existing fixture has no expected_check
    assert started.session_id and len(model.setup_inputs) == 1


FRESH = {**FOLLOW_UP, "problem": BED, "target_gap": "transfer", "target_step": "set_up",
         "hidden_rubric": ["Sets up w(2w - 4) = 120.", LIVE_WRONG_ANSWER], "expected_check": LIVE_WRONG.model_dump()}
FRESH_RIGHT = {**FRESH, "hidden_rubric": ["Sets up w(2w - 4) = 120.", RIGHT_ANSWER],
               "expected_check": RIGHT.model_dump()}
FOLLOW_UP_INPUT = FollowUpInput(problem=RECTANGLE, concept_name="Quadratic equations",
                                solution_steps=["w(w + 2) = 48", "w = 6"], student_answers=["w(w + 2) = 48"])


def test_an_invalid_fresh_problem_rubric_is_regenerated_and_never_judged_against():
    model, verifier = ScriptedModel([], follow_ups=[FRESH, FRESH_RIGHT]), FakeVerifier(follow_up_checks=[FOLLOW_UP_OK])
    draft, _, attempts = asyncio.run(write_follow_up(FOLLOW_UP_INPUT, model.model, verifier.model))
    assert draft.hidden_rubric[-1] == RIGHT_ANSWER and "expected_check" not in draft.model_dump()
    assert model.follow_up_inputs[1]["retry_reason"] == "invalid_followup" and "96" in model.follow_up_inputs[1]["retry_note"]
    assert [v["hidden_rubric"][-1] for v in verifier.follow_up_inputs] == [RIGHT_ANSWER]  # 8 × 12 went nowhere
    assert attempts[0].failure.startswith("code: ")


def test_a_fresh_problem_whose_rubric_stays_invalid_is_unavailable_not_used():
    model, verifier = ScriptedModel([], follow_ups=[FRESH]), FakeVerifier()
    with pytest.raises(FollowUpUnavailable):
        asyncio.run(write_follow_up(FOLLOW_UP_INPUT, model.model, verifier.model))
    assert verifier.follow_up_inputs == []
