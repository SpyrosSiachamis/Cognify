"""The hidden solution is the answer the set-up step's own steps reach (a stated-first guess once became the
hidden solution, and diagnosis then marked correct student work wrong to explain the difference)."""

import asyncio

import pytest

from app.tutor.agent import AgentTutor
from app.tutor.setup import SetupOutput, result_matches_steps

from .fakes import ScriptedModel

JACKET = ("A jacket costs $150. A store gives a 20% discount, then adds an $8 shipping fee. The customer uses a $20 "
          "coupon, and then 10% sales tax is applied to the amount after the coupon. What is the final amount?")
STEPS = ["20% of $150 = $30, so $150 - $30 = $120", "$120 + $8 = $128", "$128 - $20 = $108",
         "10% of $108 = $10.80, so $108 + $10.80 = $118.80"]
GUESSED = {"concept_name": "Percentage discounts", "steps": STEPS, "result": "$129.80"}
WORKED = {"concept_name": "Percentage discounts", "steps": STEPS, "result": "$118.80"}


def test_the_steps_come_before_the_result_in_what_the_model_is_asked_for():
    assert list(SetupOutput.model_json_schema()["properties"]) == ["concept_name", "steps", "result", "expected_check"]


@pytest.mark.parametrize("result, matches", [
    ("$118.80", True), ("118.8", True), ("$129.80", False), ("$132", False),
    ("x = 5", False), ("The ball stops at its highest point", True),  # no number: not checked
])
def test_a_numeric_result_must_be_what_the_last_step_reaches(result, matches):
    output = SetupOutput(concept_name="c", steps=STEPS if "x" not in result else ["x^2 = 16", "x = 4 or x = -4"], result=result)
    assert result_matches_steps(output) is matches


def test_a_result_the_steps_contradict_is_sent_back_once_and_the_worked_one_is_kept(store):
    model = ScriptedModel([], setup=[GUESSED, WORKED])
    setup = asyncio.run(AgentTutor(store, model.model).set_up(JACKET, None))
    assert setup.solution.result == "$118.80" and len(model.setup_inputs) == 2


def test_a_result_that_stays_contradicted_fails_the_set_up_instead_of_becoming_the_solution(store):
    model = ScriptedModel([], setup=[GUESSED])
    with pytest.raises(RuntimeError, match="set_up failed"):
        asyncio.run(AgentTutor(store, model.model).set_up(JACKET, None))
