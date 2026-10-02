"""Complete required solution evidence + correct final answer + no contradictory evidence => PROBLEM_RESOLVED.

Replays the live rectangle session (rectangle_complete_case.json: every answer, the tutor message each answered and
the diagnosis model's own proposals, as traced). In one answer the student wrote the whole solution: w² + 2w - 48 = 0,
(w + 8)(w - 6) = 0, each factor set to zero, w = 6 since a width cannot be negative, and the length w + 2 = 8. Live,
the problem stayed open and the probe replies invented one proof obligation after another ("why this is the only
pair", "why no other positive width"). Two code defects, neither about the wording:

- required_targets read an equation step ("Bring all terms to one side: w² + 2w - 48 = 0.") as ending at the
  quantity 0, the number on one side of the equation. No work ever "reaches" 0, so the target never moved. An
  equation step's target is now the equation itself, shown by the student writing the same equation in any form.
- worked_roots required w = 6 to satisfy every equation written, including the other case "w + 8 = 0", so a correctly
  solved factorization showed no root at all. A case of the same split no longer counts against a root.

The required targets come from the structured solution only; nothing the tutor asks afterwards is one, and once the
problem is resolved the tutor asks nothing more (the fixed acknowledgement, then the fresh problem).
"""

import asyncio
import json
from pathlib import Path

import pytest

from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest, Solution
from app.tutor.agent import AgentTutor
from app.tutor.evidence import numeric_values
from app.tutor.resolution import required_targets, standing
from app.tutor.schema import TutorDiagnosis
from app.user.service import SessionService

from .fakes import FOLLOW_UP_OK, FakeVerifier, ScriptedModel, diagnosis
from .test_transfer_regressions import COOKIES

CASE = json.loads((Path(__file__).parent / "rectangle_complete_case.json").read_text(encoding="utf-8"))
PROBLEM, TURNS, PROPOSALS = CASE["problem"], CASE["turns"], CASE["proposals"]
SOLUTION = Solution(result=CASE["solution_result"], steps=CASE["solution_steps"])
SETUP = {"concept_name": CASE["concept_name"], "steps": CASE["solution_steps"], "result": CASE["solution_result"]}
COMPLETE = 3  # the turn with the whole solution
GIVEN = set(numeric_values(PROBLEM))


def session(store):
    model = ScriptedModel(PROPOSALS, replies=["How could you check it?"], setup=SETUP, follow_ups=[COOKIES])
    svc = SessionService(AgentTutor(store, model.model, FakeVerifier(follow_up_checks=[FOLLOW_UP_OK]).model), store,
                         tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id
    return svc, sid, model


def diagnosed(store, sid):
    return [e.payload for e in store.list_trace_events(sid) if e.event_type == "DIAGNOSIS_RESULT"][-1]


# ---- the live session ----


def test_the_complete_solution_resolves_the_problem_and_the_tutor_asks_nothing_more(store):
    svc, sid, model = session(store)
    for text in TURNS[:COMPLETE]:
        assert asyncio.run(svc.attempt(sid, text)).phase == "teach"
    taught = model.teaching_calls
    turn = asyncio.run(svc.attempt(sid, TURNS[COMPLETE]))
    d = diagnosed(store, sid)
    assert d.resolution_state == "PROBLEM_RESOLVED" and d.current_target is None
    assert d.mode == "acknowledge" and model.teaching_calls == taught  # no probe, so no invented obligation
    assert turn.phase == "stress_test" and turn.follow_up.problem == COOKIES["problem"]
    assert {6.0, 8.0} <= set(d.demonstrated_values)


def test_the_required_targets_are_the_solutions_own_steps():
    targets = required_targets(SOLUTION, GIVEN)
    assert [t.step for t in targets] == SOLUTION.steps[4:]  # the two equations, w = 6 and the length
    assert [t.value for t in targets] == [None, None, 6.0, 8.0]  # the 0 of "... = 0" is no quantity
    assert all(t.step in SOLUTION.steps for t in targets)


# ---- the invariant, split over turns, with a verification last ----

SET_UP = "The area is w(w + 2) = 48, so w² + 2w - 48 = 0."
SOLVED = "(w + 8)(w - 6) = 0, so w + 8 = 0 or w - 6 = 0, so w = -8 or w = 6. A width cannot be negative, so w = 6."
VERIFIED = "The length is w + 2 = 8. Check: 6 × 8 = 48, and 8 is 2 m greater than 6, so both conditions hold."


def read(*steps: tuple[str, str, str]) -> TutorDiagnosis:
    return TutorDiagnosis.model_validate(diagnosis(*steps, gap=None) | {"response_to": "tutor_question"})


def stand(attempt: str, reading: TutorDiagnosis, earlier: list[str]):
    return standing(SOLUTION, PROBLEM, reading, attempt, earlier, earlier)


def test_complete_evidence_then_a_verification_resolves_with_no_extra_target():
    after_two = stand(SOLVED, read(("compute", "correct", SOLVED)), [SET_UP])
    assert after_two.state != "PROBLEM_RESOLVED" and after_two.current_target == SOLUTION.steps[-1]  # the length
    last = stand(VERIFIED, read(("compute", "correct", "w + 2 = 8"), ("interpret", "correct", "6 × 8 = 48")),
                 [SET_UP, SOLVED])
    assert last.state == "PROBLEM_RESOLVED" and last.current_target is None


def test_once_shown_a_verification_adds_no_target_and_keeps_it_resolved():
    complete = TURNS[COMPLETE]
    check = "6 × 8 = 48, and 8 is 2 meters greater than 6, so the dimensions satisfy both conditions."
    result = stand(check, read(("compute", "correct", "6 × 8 = 48")), [complete])
    assert result.state == "PROBLEM_RESOLVED" and result.current_target is None


@pytest.mark.parametrize("answer, why", [
    ("w² + 2w - 48 = 0, so (w + 6)(w - 8) = 0, so w + 6 = 0 or w - 8 = 0, so w = -6 or w = 8. The length is "
     "w + 2 = 10.", "a wrong factorization: 8 fails the student's own quadratic"),
    ("w² + 2w - 48 = 0 factors as (w + 6)(w - 8) = 0, so w = 6, and the length is w + 2 = 8.",
     "the right values next to an equation they contradict"),
    ("w² + 2w - 48 = 0, so (w + 8)(w - 6) = 0, so w = 6.", "no length: the final answer is not complete"),
    ("The width is w = 6 and the length is 8.", "values stated with nothing behind them"),
])
def test_anything_short_of_complete_consistent_evidence_does_not_resolve(answer, why):
    assert stand(answer, read(("compute", "correct", answer)), []).state != "PROBLEM_RESOLVED", why


def test_a_wrong_step_keeps_the_problem_open_even_with_every_value_shown():
    reading = TutorDiagnosis.model_validate(
        diagnosis(("compute", "correct", "w = 6"), ("interpret", "wrong", "So the dimensions are 6 m by 8 m."),
                  gap="representation") | {"response_to": "tutor_question"})
    assert stand(TURNS[COMPLETE], reading, []).state != "PROBLEM_RESOLVED"
