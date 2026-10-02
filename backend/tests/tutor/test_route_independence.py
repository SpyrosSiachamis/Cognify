"""A required step is shown by any valid route: later worked evidence that entails it, or the final result, covers it.

The live rectangle session (w(w + 2) = 48): the hidden solution used the quadratic formula (discriminant 196,
√196 = 14), the student factored, and the session could never resolve because 196 was "required". Now a route the
student worked covers the hidden route's steps; a stated value, wrong algebra or a contradiction never does. In the
two wrong-work cases the scripted diagnosis even marks everything correct, so the code check is what catches them.
"""

import asyncio

import pytest

from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest
from app.tutor.agent import AgentTutor
from app.user.service import SessionService

from .fakes import APPROVE, FOLLOW_UP_OK, FakeVerifier, ScriptedModel, diagnosis
from .test_transfer_regressions import COOKIES

PROBLEM = "A rectangle has an area of 48 m². Its length is 2 m greater than its width. Find its dimensions."
LENGTH_STEP = "Length = 6 + 2 = 8"
SETUP = {"concept_name": "Quadratic equations", "steps": [
    "Width w, length w + 2, so w(w + 2) = 48", "w² + 2w − 48 = 0", "Discriminant b² − 4ac = 4 + 192 = 196",
    "√196 = 14", "w = (−2 + 14)/2 = 6", LENGTH_STEP], "result": "Width = 6 m, Length = 8 m"}

FORMULA = ("Let the width be w, so w(w + 2) = 48, so w² + 2w − 48 = 0. The discriminant is 4 + 192 = 196, and "
           "√196 = 14, so w = (−2 + 14)/2 = 6. The length is w + 2 = 8.")
FACTORING = ("w(w + 2) = 48, so w² + 2w − 48 = 0. Factoring gives (w + 8)(w − 6) = 0, so w = 6 because a width "
             "cannot be negative. The length is w + 2 = 8.")
COMPLETING_SQUARE = ("w² + 2w = 48, so w² + 2w + 1 = 49, so (w + 1)² = 49, so w + 1 = 7 and w = 6. "
                     "The length is w + 2 = 8.")
BARE = "The width is w = 6 and the length is 8."
WRONG_FACTORING = "w² + 2w − 48 = 0, so (w + 6)(w − 8) = 0, so w = 8, and the length is w + 2 = 10."
CONTRADICTORY = "w² + 2w − 48 = 0 factors as (w + 6)(w − 8) = 0, so w = 6, and the length is w + 2 = 8."
# The live turn: factored correctly, but never stated the length.
LIVE_TURN = ("w² + 2w − 48 = 0. Factoring gives (w + 8)(w − 6) = 0, so w = 6 or w = −8. Since a width can't be "
             "negative, w = 6.")


def all_correct(text: str) -> dict:
    """The diagnosis model reading the whole answer as one correct step (no gap): code alone decides resolution."""
    return diagnosis(("compute", "correct", text), gap=None) | {"response_to": "original_problem"}


def standing_after(store, text: str):
    model = ScriptedModel([all_correct(text)], replies=["What is the length?"], setup=SETUP, follow_ups=[COOKIES])
    svc = SessionService(AgentTutor(store, model.model, FakeVerifier(APPROVE, follow_up_checks=[FOLLOW_UP_OK]).model),
                         store, tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id
    turn = asyncio.run(svc.attempt(sid, text))
    diagnosed = [e.payload for e in store.list_trace_events(sid) if e.event_type == "DIAGNOSIS_RESULT"][-1]
    return turn, diagnosed


@pytest.mark.parametrize("route", [FORMULA, FACTORING, COMPLETING_SQUARE], ids=["formula", "factoring", "square"])
def test_any_worked_route_resolves(store, route):
    """The quadratic formula (the hidden route), factoring, and completing the square (different intermediate values)."""
    turn, d = standing_after(store, route)
    assert d.resolution_state == "PROBLEM_RESOLVED" and turn.phase == "stress_test"


@pytest.mark.parametrize("answer", [BARE, WRONG_FACTORING, CONTRADICTORY], ids=["bare", "wrong", "contradictory"])
def test_a_stated_value_or_false_algebra_does_not_resolve(store, answer):
    """A bare final answer (nothing shows how it was found), wrong factoring (8 fails w² + 2w − 48 = 0), and the right
    answer next to contradictory reasoning (6 fails (w + 6)(w − 8) = 0) are all read correct by the scripted model."""
    turn, d = standing_after(store, answer)
    assert d.resolution_state != "PROBLEM_RESOLVED" and turn.phase == "teach"


def test_the_live_factoring_turn_covers_the_formula_steps_and_asks_for_the_length(store):
    """The hidden route's discriminant is no longer the target: the length is (the student never stated it)."""
    turn, d = standing_after(store, LIVE_TURN)
    assert d.current_target == LENGTH_STEP and turn.phase == "teach"
    assert 6.0 in d.demonstrated_values


def test_a_bare_final_answer_after_the_set_up_in_an_earlier_turn_still_does_not_resolve(store):
    setup_turn = diagnosis(("set_up", "correct", "w(w + 2) = 48"), gap=None) | {"response_to": "original_problem"}
    model = ScriptedModel([setup_turn, all_correct(BARE)], replies=["And then?"], setup=SETUP, follow_ups=[COOKIES])
    svc = SessionService(AgentTutor(store, model.model, FakeVerifier(APPROVE, follow_up_checks=[FOLLOW_UP_OK]).model),
                         store, tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id
    asyncio.run(svc.attempt(sid, "w(w + 2) = 48"))
    assert asyncio.run(svc.attempt(sid, BARE)).phase == "teach"  # 6 satisfies the equation, but nothing derives it here


# ---- the two policy decisions, checked directly on code's reading ----

from app.session.schema import Solution  # noqa: E402
from app.tutor.resolution import standing  # noqa: E402
from app.tutor.schema import TutorDiagnosis  # noqa: E402

BALL = "A ball is thrown upward at 20 m/s. How high does it go? (Use g = 9.8 m/s^2)"
BALL_SOLUTION = Solution(result="20.4 m", steps=["At the highest point v = 0.", "Use v^2 = u^2 - 2gh.",
                                                  "h = 400 / 19.6 = 20.4 m."])
BOOKS = ("A box contains 41 books. 5 damaged books are thrown away, then 12 books are removed. The remaining books "
         "are placed equally on 6 shelves. How many books are on each shelf?")
BOOKS_SOLUTION = Solution(result="4 books", steps=["41 - 5 = 36 books are left.", "36 - 12 = 24 books remain.",
                                                    "24 ÷ 6 = 4.", "4 books on each shelf."])


def read(problem, solution, text):
    d = TutorDiagnosis.model_validate(all_correct(text))
    return standing(solution, problem, d, text, [], []).state


def test_a_named_method_with_the_final_value_resolves_and_the_value_alone_does_not():
    maria = "With 2.04 s known I could use v^2 = u^2 - 2gh, so h = 20.4 m."
    assert read(BALL, BALL_SOLUTION, maria) == "PROBLEM_RESOLVED"
    assert read(BALL, BALL_SOLUTION, "At the highest point, v = 0, so h = 20.4 m.") != "PROBLEM_RESOLVED"


def test_a_calculation_covers_skipped_steps_only_when_its_inputs_are_accounted_for():
    """A lone "24 ÷ 6 = 4": 24 is not a given and was never written before (12 + 12 = 24 is a coincidence)."""
    assert read(BOOKS, BOOKS_SOLUTION, "24 ÷ 6 = 4") != "PROBLEM_RESOLVED"
    full = "41 - 5 = 36 books are left, 36 - 12 = 24 remain, and 24 ÷ 6 = 4 books on each shelf."
    assert read(BOOKS, BOOKS_SOLUTION, full) == "PROBLEM_RESOLVED"
