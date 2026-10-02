"""Correct evidence does not silently turn wrong. A step the model marks wrong that states a value the problem's
working really reaches (the worked solution's values, or results the student already showed correctly), uses no
other number and has true arithmetic, is asked about once; the model's second answer stands, so a genuine error is
still caught. New values (a contradiction, a wrong result) are never covered.

From the live jacket session: "$120 + $8 = $128", "$128." and finally an established "$120" were marked wrong.
"""

import asyncio

import pytest

from app.tutor.agent import AgentTutor, reached_values
from app.tutor.evidence import arithmetic_holds, numeric_values
from app.tutor.reasoning import apply_rules
from app.tutor.schema import ReasoningDraft, ReasoningInput, Step
from app.session.schema import Solution

from .conftest import teach_request
from .fakes import APPROVE, FakeVerifier, ScriptedModel
from .test_transfer_regressions import proc

JACKET = ("A jacket costs $150. A store gives a 20% discount, then adds an $8 shipping fee. The customer uses a $20 "
          "coupon, and then 10% sales tax is applied to the amount after the coupon. What is the final amount?")
SOLUTION = Solution(result="$118.80", steps=["20% of $150 = $30, so $150 - $30 = $120", "$120 + $8 = $128",
                                             "$128 - $20 = $108", "10% of $108 = $10.80, so $108 + $10.80 = $118.80"])
GIVEN = frozenset(numeric_values(JACKET))
REACHED = frozenset(numeric_values(" ".join([SOLUTION.result, *SOLUTION.steps])))


FINAL = frozenset(numeric_values(SOLUTION.result))


def rules(attempt, *steps, gap="representation", given=GIVEN, reached=REACHED, final=FINAL, recheck=True,
          response_to="original_problem"):
    draft = ReasoningDraft.model_validate(proc(*steps, gap=gap, response_to=response_to))
    return apply_rules(draft, attempt, recheck=recheck, has_tutor_message=response_to != "original_problem",
                       given=given, reached=reached, final=final)


def asked_about(attempt, *steps, **kw) -> str | None:
    try:
        rules(attempt, *steps, **kw)
    except ValueError as exc:
        return str(exc)
    return None


# ---- the six cases ----


def test_case_1_a_terse_result_answering_the_tutors_question_is_correct():
    """The jacket turn: "$128." answers "what is $120 + $8?" It cannot be false, so code settles it (no ask)."""
    text = "$120 + $8 = $128. $128."
    d = rules(text, ("compute", "correct", "$120 + $8 = $128"), ("interpret", "wrong", "$128."),
              response_to="tutor_question")
    assert [s.status for s in d.steps] == ["correct", "correct"] and d.error is None


def test_case_1_as_the_answer_to_the_whole_problem_a_terse_intermediate_value_is_the_models_call():
    """Sent as the whole answer, "$128." is not the final amount: code asks once and the model's answer stands."""
    text = "$120 + $8 = $128. $128."
    ask = asked_about(text, ("compute", "correct", "$120 + $8 = $128"), ("interpret", "wrong", "$128."))
    assert ask is not None and '"$128."' in ask and "terse result line" in ask


def test_case_2_an_explicit_conclusion_the_calculation_reached_is_asked_about():
    problem_values = frozenset({14.0, 10.0})
    reached = frozenset({1.4, 15.4})
    text = "$14 + $1.40 = $15.40. Therefore $15.40 is the final amount."
    steps = (("compute", "correct", "$14 + $1.40 = $15.40"), ("interpret", "wrong", "Therefore $15.40 is the final amount."))
    # It states exactly the final answer, after the calculation that reaches it: code settles it as correct.
    d = rules(text, *steps, given=problem_values, reached=reached, final=frozenset({15.4}))
    assert [s.status for s in d.steps] == ["correct", "correct"]
    # Where $15.40 is a value on the way rather than the final answer, the model is asked once.
    ask = asked_about(text, *steps, given=problem_values, reached=reached, final=frozenset({44.0}))
    assert ask is not None and "Therefore $15.40 is the final amount." in ask


def test_case_3_an_implicit_step_is_missing_not_wrong():
    text = "The discounted price is $120. After the shipping fee and coupon, $108 remains."
    ask = asked_about(text, ("compute", "correct", "The discounted price is $120."),
                      ("set_up", "wrong", "After the shipping fee and coupon, $108 remains."),
                      ("substitute", "missing", None), gap="procedure")
    assert ask is not None and "$108 remains" in ask
    # Answered as correct, the unwritten arithmetic stays missing: incomplete, not wrong.
    d = rules(text, ("compute", "correct", "The discounted price is $120."),
              ("set_up", "correct", "After the shipping fee and coupon, $108 remains."),
              ("substitute", "missing", None), gap="procedure", recheck=False)
    assert [(s.role, s.status) for s in d.steps] == [("compute", "correct"), ("set_up", "correct"),
                                                      ("substitute", "missing")]


def test_case_4_a_result_established_in_an_earlier_turn_stays_trusted():
    """Turn 1 showed "$120" correctly; in turn 3 the model marked that same "$120" wrong. Even with a worked solution
    that never wrote 120, the student's own earlier correct result is a reached value."""
    request = teach_request("$120 + $8 = $128.", problem=JACKET,
                            solution=Solution(result="$118.80", steps=["$128 - $20 = $108", "$108 × 1.1 = $118.80"]),
                            earlier_correct_steps=[Step(role="compute", status="correct", quote="The discounted price is $120")])
    reached = frozenset(reached_values(request))
    assert 120.0 in reached
    text = "The $128 is correct because $120 + $8 = $128."
    steps = (("identify_quantities", "wrong", "$120"), ("compute", "correct", "$120 + $8 = $128"))
    d = rules(text, *steps, reached=reached, response_to="tutor_question")
    assert [s.status for s in d.steps] == ["correct", "correct"]  # the established $120 is not turned wrong
    # The same step in the student's own words (not a bare value) is asked about once instead.
    ask = asked_about("The price after the discount is $120.", ("compute", "wrong", "The price after the discount is $120."),
                      reached=reached, final=frozenset())
    assert ask is not None and "$120" in ask


def test_case_5_a_contradiction_with_a_new_value_is_not_covered():
    text = "The discounted price was actually $130. $130 + $8 = $138."
    assert asked_about(text, ("compute", "wrong", "The discounted price was actually $130."),
                       ("compute", "wrong", "$130 + $8 = $138")) is None
    d = rules(text, ("compute", "wrong", "The discounted price was actually $130."), recheck=False)
    assert [s.status for s in d.steps] == ["wrong"]  # the earlier $120 is not immutable: the change is flagged


def test_case_6_a_conclusion_that_contradicts_its_calculation_stays_wrong():
    text = "$120 + $8 = $128. Therefore the amount after shipping is $138."
    assert asked_about(text, ("compute", "correct", "$120 + $8 = $128"),
                       ("interpret", "wrong", "Therefore the amount after shipping is $138.")) is None


# ---- what is and is not covered ----


def test_false_arithmetic_is_not_covered_even_with_reached_values():
    assert not arithmetic_holds("$120 + $8 = $129")
    assert asked_about("$120 + $8 = $118.80", ("compute", "wrong", "$120 + $8 = $118.80")) is None
    assert arithmetic_holds("0.10 × 108 = 10.80") and arithmetic_holds("24 ÷ 6 = 4") and not arithmetic_holds("24 ÷ 6 = 5")


def test_restating_only_the_givens_is_not_covered():
    """Choosing the wrong givens is a real error: "$150 + $8" says nothing the working reached."""
    assert asked_about("I add $150 + $8 first.", ("set_up", "wrong", "I add $150 + $8 first.")) is None


def test_the_correct_final_answer_alone_with_no_work_is_left_to_the_model():
    """A bare final answer is a guess, not evidence: code does not turn it correct."""
    d = rules("$118.80", ("interpret", "wrong", "$118.80"), recheck=False)
    assert [s.status for s in d.steps] == ["wrong"]


def test_the_second_answer_stands_so_a_real_error_can_stay_wrong():
    """An intermediate value called the final answer: asked about once, and the model may keep it wrong."""
    text = "$120 + $8 = $128. The final amount is $128."
    steps = (("compute", "correct", "$120 + $8 = $128"), ("interpret", "wrong", "The final amount is $128."))
    assert asked_about(text, *steps) is not None
    d = rules(text, *steps, recheck=False)
    assert ("interpret", "wrong") in [(s.role, s.status) for s in d.steps]


def test_the_values_are_never_sent_to_the_model():
    sent = ReasoningInput(problem="p", attempt="a", final_answer="4", given_values=[1.0], reached_values=[2.0]).prompt()
    assert "given_values" not in sent and "reached_values" not in sent


# ---- in the agent ----


def test_the_agent_asks_once_and_takes_the_corrected_reading(store):
    worded = "So the price after shipping is $128."
    false_positive = proc(("compute", "correct", "$120 + $8 = $128"), ("interpret", "wrong", worded),
                          gap="representation", response_to="tutor_question")
    corrected = proc(("compute", "correct", "$120 + $8 = $128"), ("interpret", "correct", worded), gap=None,
                     response_to="tutor_question")
    model = ScriptedModel([false_positive, corrected], replies=["What do you do with the $20 coupon next?"],
                          setup={"concept_name": "c", "steps": SOLUTION.steps, "result": SOLUTION.result})
    tutor = AgentTutor(store, model.model, FakeVerifier(APPROVE).model)
    request = teach_request(f"The $8 shipping fee is added to the discounted price: $120 + $8 = $128. {worded}",
                            problem=JACKET, solution=SOLUTION, tutor_message="What is $120 + $8?", first_thought=False)
    result, trace = asyncio.run(tutor.teach_with_trace(request))
    assert model.reasoning_calls == 2
    assert not any(s.status == "wrong" for s in result.output.steps)
    assert "given_values" not in model.reasoning_inputs[0] and "reached_values" not in model.reasoning_inputs[0]


def test_the_agent_settles_a_bare_sub_answer_without_asking_again(store):
    false_positive = proc(("compute", "correct", "$120 + $8 = $128"), ("interpret", "wrong", "$128."),
                          gap="representation", response_to="tutor_question")
    model = ScriptedModel([false_positive], replies=["What do you do with the $20 coupon next?"])
    tutor = AgentTutor(store, model.model, FakeVerifier(APPROVE).model)
    request = teach_request("$120 + $8 = $128. $128.", problem=JACKET, solution=SOLUTION,
                            tutor_message="What is $120 + $8?", first_thought=False)
    result, _ = asyncio.run(tutor.teach_with_trace(request))
    assert model.reasoning_calls == 1 and not any(s.status == "wrong" for s in result.output.steps)


@pytest.mark.parametrize("text, values", [("$1,250.50 and 20%", {1250.5, 20.0}), ("€10.45", {10.45}), ("no numbers", set())])
def test_numbers_are_read_from_the_students_words(text, values):
    assert numeric_values(text) == values
