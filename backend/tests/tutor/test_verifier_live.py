"""The reply verifier on hand-written drafts: semantic method adherence and targeting.

    docker compose exec backend python -m pytest -m live tests/tutor/test_verifier_live.py -v -s
"""

import asyncio
import os

import pytest

from app.ai_gateway import gateway
from app.tutor.methods import METHOD_DEFINITIONS
from app.verification.agent import check_reply
from app.verification.schema import ReplyCheckInput

from .conftest import MARIA_FIRST_THOUGHT, PROBLEM, SOLUTION

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("TUTOR_MODEL_ID"), reason="set TUTOR_MODEL_ID to a Bedrock model ID"),
]

GAP_STEP = 'choose_method (missing): "I don\'t know how to get the height from the time"'


def check(reply: str, method: str):
    checked = asyncio.run(check_reply(ReplyCheckInput(
        problem=PROBLEM, attempt=MARIA_FIRST_THOUGHT, reply=reply, method=method, hints_used=0,
        hidden_solution=" ".join(SOLUTION.steps), main_gap="recognition", gap_step=GAP_STEP,
        method_definition=METHOD_DEFINITIONS[method], language="English",
    ), gateway.model_for()))
    print(checked)
    assert checked.ok
    return checked.value


def test_a_plain_question_is_not_visual_decomposition():
    result = check("You found the time to the top. What other quantities might help you find the height?",
                   "visual_decomposition")
    assert not result.approved and result.reason == "method_drift"


def test_decomposition_without_the_word_sketch_is_accepted():
    result = check(
        "You have the time to the top. Make two columns: what you know at launch and what you know at the "
        "highest point, and put the height you want in a third column marked '?'. Which column entries "
        "could link straight to that '?' without the time?",
        "visual_decomposition",
    )
    assert result.approved, result.note


def test_a_generic_move_is_off_target():
    result = check("Great effort! Remember that physics problems get easier with practice. What topic is this?",
                   "socratic")
    assert not result.approved and result.reason in ("off_target", "method_drift")


def test_a_targeted_socratic_question_is_accepted():
    result = check(
        "You already have the time to the top. During that time, how fast is the ball moving on average, "
        "and how could that help you find how far it went?",
        "socratic",
    )
    assert result.approved, result.note



# ---- strategy generalization: method x domain, judged by what the move does ----

SCENARIOS = {
    "algebra": dict(problem="Solve for x: 3x + 5 = 20.", attempt="I got 3x = 15 but I don't know what to do next.",
                    main_gap="procedure", gap_step='compute (missing): "I don\'t know what to do next"',
                    solution="Subtract 5: 3x = 15. Divide by 3: x = 5."),
    "fractions": dict(problem="Work out 1/2 + 1/3.", attempt="1/2 + 1/3 = 2/5, I added the tops and the bottoms.",
                      main_gap="concept", gap_step='compute (wrong): "1/2 + 1/3 = 2/5"',
                      solution="Common denominator 6: 3/6 + 2/6 = 5/6."),
    "car": dict(problem="A car starts from rest and accelerates at 2 m/s^2 for 5 s. How far does it travel?",
                attempt="Its speed after 5 s is 10 m/s, so it goes 10 x 5 = 50 m.", main_gap="concept",
                gap_step='set_up (wrong): "it goes 10 x 5 = 50 m"', solution="s = 1/2 a t^2 = 25 m."),
}

PERFORMS_METHOD = [  # do the method without naming it -> approved
    ("algebra", "socratic", "You have 3x = 15. What could you do to both sides so that x is left on its own?"),
    ("algebra", "visual_decomposition",
     "Draw two boxes. In the left one write what you have, 3x = 15; in the right one write what you want, x = ?. "
     "What single operation turns the left box into the right one?"),
    ("fractions", "counterexample",
     "If adding tops and bottoms worked, then 1/2 + 1/2 would be 2/4, which is only one half. "
     "Can two halves really add up to just a half?"),
    ("car", "socratic", "Your 10 m/s is the speed at the very end. Was the car going that fast for all 5 seconds?"),
    ("fractions", "worked_example",
     "Here is a simpler one: 1/4 + 1/4. Both are quarters, so the size of the pieces stays the same: one quarter "
     "plus one quarter is two quarters. Your turn: what does 2/4 simplify to? Then think about what size of piece "
     "both 1/2 and 1/3 could be written in."),
]

NAMES_BUT_DOES_NOT_PERFORM = [  # use the method's vocabulary without doing it -> rejected
    ("algebra", "visual_decomposition", "Let's visualise it and break it down: what is x?"),
    ("algebra", "worked_example", "Here is a worked example for you: what is x in 3x = 15?"),
    ("fractions", "counterexample", "Here is a counterexample to think about: what is a common denominator?"),
    ("car", "socratic", "Let me explain: the car speeds up from 0, so use its average speed of 5 m/s instead of 10 m/s."),
]


def scenario_check(domain: str, method: str, reply: str):
    sc = SCENARIOS[domain]
    checked = asyncio.run(check_reply(ReplyCheckInput(
        problem=sc["problem"], attempt=sc["attempt"], reply=reply, method=method, hints_used=0,
        hidden_solution=sc["solution"], main_gap=sc["main_gap"], gap_step=sc["gap_step"],
        method_definition=METHOD_DEFINITIONS[method], language="English",
    ), gateway.model_for()))
    print(domain, method, checked)
    assert checked.ok
    return checked.value


@pytest.mark.parametrize(("domain", "method", "reply"), PERFORMS_METHOD, ids=[f"{d}-{m}" for d, m, _ in PERFORMS_METHOD])
def test_a_reply_that_performs_the_method_is_approved(domain, method, reply):
    result = scenario_check(domain, method, reply)
    assert result.approved, result.note


@pytest.mark.parametrize(("domain", "method", "reply"), NAMES_BUT_DOES_NOT_PERFORM,
                         ids=[f"{d}-{m}" for d, m, _ in NAMES_BUT_DOES_NOT_PERFORM])
def test_naming_a_method_without_performing_it_is_rejected(domain, method, reply):
    result = scenario_check(domain, method, reply)
    assert not result.approved, "named the method but did not perform it"


# ---- the student check judges the gap step, not just the answer (F16) ----

STRESS = dict(
    follow_up="A stone is launched straight up at 15 m/s from a balcony. How far above the balcony does it rise? "
    "(Use g = 9.8 m/s^2)",
    concept_invariant="Constant-acceleration motion: relate speeds and distance without needing the time.",
    hidden_rubric=["Uses v^2 = u^2 - 2gh with v = 0 at the top", "Substitutes u = 15", "About 11.5 m"],
    target_gap="recognition", target_step="choose_method",
)


def student_check(text: str):
    from app.verification.agent import check_student
    from app.verification.schema import StudentCheckInput

    checked = asyncio.run(check_student(StudentCheckInput(**STRESS, student_text=text), gateway.model_for()))
    print(checked)
    assert checked.ok
    return checked.value


def test_a_reasoned_solution_shows_the_gap_step():
    result = student_check("At the top v = 0, so v^2 = u^2 - 2gh gives 0 = 225 - 19.6h, h = 225 / 19.6, about 11.5 m.")
    assert result.correct and result.own_work


def test_a_correct_answer_by_trial_and_error_is_not_own_work():
    result = student_check("I tried some heights: 10 m felt too low and 12 m too high, so I guess about 11.5 m.")
    assert not result.own_work


# ---- a probe asks about the student's thinking only (a hint in it would be uncounted help) ----


def test_a_probe_that_slips_in_a_hint_is_rejected():
    checked = asyncio.run(check_reply(ReplyCheckInput(
        problem=PROBLEM, attempt="I don't know.", reply="The ball slows down by 9.8 m/s every second. What is its speed at the very top?",
        method=None, hints_used=0, hidden_solution=" ".join(SOLUTION.steps), main_gap=None, language="English",
    ), gateway.model_for()))
    print(checked)
    assert checked.ok and not checked.value.approved and checked.value.reason == "heavy_hint"


def test_a_probe_that_only_asks_about_their_thinking_is_approved():
    checked = asyncio.run(check_reply(ReplyCheckInput(
        problem=PROBLEM, attempt="I don't know.", reply="What do you notice first when you read the problem?",
        method=None, hints_used=0, hidden_solution=" ".join(SOLUTION.steps), main_gap=None, language="English",
    ), gateway.model_for()))
    print(checked)
    assert checked.ok and checked.value.approved, checked.value.note
