"""Support is removed only when the problem is resolved by the student's own demonstrated work.

The live 420-tablet session (tablets_case.json: the problem, the student's four answers and the diagnosis model's own
proposals, as traced) went to a fresh problem after "I got no clue", because a turn count removed support. Now the
state is read from the student's evidence: earlier correct steps stay earlier correct steps, the open step stays open,
and neither "no error found", a fixed step alone, a number of turns nor the final answer alone resolves the problem.
"""

import asyncio
import json
from pathlib import Path

import pytest

from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest
from app.tutor.agent import AgentTutor
from app.user.errors import ApiError
from app.user.service import MAX_TEACH_TURNS, OFFER_EXIT, SessionService

from .fakes import APPROVE, FOLLOW_UP_OK, FakeVerifier, ScriptedModel, diagnosis
from .test_transfer_regressions import COOKIES

CASE = json.loads((Path(__file__).parent / "tablets_case.json").read_text(encoding="utf-8"))
PROBLEM, TURNS, PROPOSALS = CASE["problem"], CASE["turns"], CASE["proposals"]
RATIO_STEP = "378 × 3/7 = 162 tablets for Room A"
SETUP = {"concept_name": "Percentages and ratios", "steps": [
    "10% of 420 = 42 tablets damaged", "420 - 42 = 378 tablets remain", RATIO_STEP, "378 × 4/7 = 216 tablets for Room B",
    "162 × 1.2 = 194.4 tablets for Room A", "5% of 420 = 21 tablets transferred", "194.4 + 21 = 215.4 tablets for Room A",
    "216 - 21 = 195 tablets for Room B"], "result": "Room A: 215.4 tablets, Room B: 195 tablets"}

RATIO = "Room A gets 378 × 3/7 = 162 and Room B gets 378 × 4/7 = 216."
FINISH = ("Room A: 162 × 1.2 = 194.4. The transfer is 5% of 420 = 21. Room A: 194.4 + 21 = 215.4, "
          "Room B: 216 - 21 = 195.")
FULL = f"10% of 420 = 42, so 420 - 42 = 378 remain. {RATIO} {FINISH}"
NOTHING = diagnosis(("choose_method", "missing", None), gap=None, confidence="low", evidence="insufficient")


def correct(text: str, *quotes: str, response_to: str = "tutor_question") -> dict:
    """A scripted reading that marks the given quotes of the answer correct (no gap)."""
    return diagnosis(*(("compute", "correct", q) for q in quotes), gap=None) | {"response_to": response_to}


def session(store, proposals, replies=("What do you do next?",), setup=SETUP):
    model = ScriptedModel(proposals, replies=list(replies), setup=setup, follow_ups=[COOKIES])
    verifier = FakeVerifier(APPROVE, follow_up_checks=[FOLLOW_UP_OK])
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store, tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id
    return svc, sid, model


def send(svc, sid, text):
    return asyncio.run(svc.attempt(sid, text))


def last(store, sid, kind):
    found = [e.payload for e in store.list_trace_events(sid) if e.event_type == kind]
    return found[-1] if found else None


def states(store, sid):
    return [e.payload.resolution_state for e in store.list_trace_events(sid) if e.event_type == "DIAGNOSIS_RESULT"]


def no_support_removed(store, sid):
    return last(store, sid, "SUPPORT_REMOVED") is None and last(store, sid, "FRESH_PROBLEM_GENERATED") is None


# ---- the live 420-tablet session ----


def test_correct_steps_then_i_got_no_clue_keeps_tutoring(store):
    """The exact sequence: the old turn cap removed support at turn 4. Now the session stays in progress."""
    svc, sid, model = session(store, PROPOSALS)
    turns = [send(svc, sid, text) for text in TURNS]
    assert [t.phase for t in turns] == ["teach"] * 4
    assert no_support_removed(store, sid) and model.follow_up_inputs == []
    assert states(store, sid) == ["CURRENT_TARGET_UNRESOLVED", "CURRENT_TARGET_RESOLVED", "CURRENT_TARGET_RESOLVED",
                                  "PREVIOUS_STEPS_CORRECT"]
    diagnosed = last(store, sid, "DIAGNOSIS_RESULT")
    assert diagnosed.current_target == RATIO_STEP and diagnosed.mode == "probe"
    assert {42.0, 378.0} <= set(diagnosed.demonstrated_values)
    assert turns[-1].message.endswith(OFFER_EXIT)  # the 4th unresolved turn offers a way out, not a fresh problem
    assert last(store, sid, "REPLY_SENT").unresolved_policy == "offer_exit"


@pytest.mark.parametrize("unresolved", ["I don't know", "I can't do this step", "Is it lunch time yet?"])
def test_correct_partial_work_then_no_progress_stays_in_progress(store, unresolved):
    """Any wording: the state is read from the evidence, not from the phrase."""
    svc, sid, _ = session(store, [PROPOSALS[1], PROPOSALS[2], NOTHING])
    send(svc, sid, TURNS[1])
    send(svc, sid, TURNS[2])
    turn = send(svc, sid, unresolved)
    assert turn.phase == "teach" and no_support_removed(store, sid)
    assert states(store, sid)[-1] == "PREVIOUS_STEPS_CORRECT"


def test_one_correct_step_then_i_dont_know_stays_in_progress(store):
    svc, sid, _ = session(store, [PROPOSALS[1], NOTHING])
    send(svc, sid, TURNS[1])
    assert send(svc, sid, "I don't know").phase == "teach" and no_support_removed(store, sid)
    assert last(store, sid, "DIAGNOSIS_RESULT").current_target == "420 - 42 = 378 tablets remain"


def test_a_blank_answer_after_partial_work_changes_nothing(store):
    svc, sid, _ = session(store, [PROPOSALS[1]])
    send(svc, sid, TURNS[1])
    assert send(svc, sid, "   ").phase == "teach" and no_support_removed(store, sid)


# ---- positive control: resolution needs every required step, then the answer ----


def test_the_ratio_step_resolves_the_target_and_the_finish_resolves_the_problem(store):
    ratio = correct(RATIO, "Room A gets 378 × 3/7 = 162", "Room B gets 378 × 4/7 = 216")
    finish = correct(FINISH, "162 × 1.2 = 194.4", "5% of 420 = 21", "Room A: 194.4 + 21 = 215.4",
                     "Room B: 216 - 21 = 195")
    svc, sid, model = session(store, [*PROPOSALS[1:3], ratio, finish])
    send(svc, sid, TURNS[1])
    send(svc, sid, TURNS[2])
    turn = send(svc, sid, RATIO)
    assert turn.phase == "teach" and states(store, sid)[-1] == "CURRENT_TARGET_RESOLVED"
    assert last(store, sid, "DIAGNOSIS_RESULT").current_target == "162 × 1.2 = 194.4 tablets for Room A"
    turn = send(svc, sid, FINISH)
    assert turn.phase == "stress_test" and states(store, sid)[-1] == "PROBLEM_RESOLVED"
    assert last(store, sid, "SUPPORT_REMOVED").reason == "problem_resolved"


def test_a_fully_worked_first_answer_goes_straight_to_the_fresh_problem(store):
    whole = correct(FULL, "10% of 420 = 42", "420 - 42 = 378", "378 × 3/7 = 162", "378 × 4/7 = 216",
                    "162 × 1.2 = 194.4", "5% of 420 = 21", "194.4 + 21 = 215.4", "216 - 21 = 195",
                    response_to="original_problem")
    svc, sid, _ = session(store, [whole])
    assert send(svc, sid, FULL).phase == "stress_test"
    assert states(store, sid) == ["PROBLEM_RESOLVED"]


def test_the_final_answer_without_the_steps_does_not_resolve_the_problem(store):
    """Adversarial: steps 1-2 shown, then the correct final answer (even marked correct); steps 3-5 never shown."""
    claim = "So Room A has 215.4 tablets and Room B has 195 tablets."
    marked_correct = correct(claim, "Room A has 215.4 tablets and Room B has 195 tablets", response_to="original_problem")
    svc, sid, model = session(store, [*PROPOSALS[1:3], marked_correct])
    send(svc, sid, TURNS[1])
    send(svc, sid, TURNS[2])
    turn = send(svc, sid, claim)
    assert turn.phase == "teach" and no_support_removed(store, sid) and model.follow_up_inputs == []
    diagnosed = last(store, sid, "DIAGNOSIS_RESULT")
    assert diagnosed.resolution_state == "CURRENT_TARGET_UNRESOLVED" and diagnosed.current_target == RATIO_STEP
    assert diagnosed.mode != "acknowledge"  # no "Next comes a fresh problem" when none follows


def test_a_repaired_step_short_of_the_answer_asks_about_the_next_step(store):
    slip = diagnosis(("compute", "correct", "420*0.1 = 42"), ("compute", "wrong", "420 - 42 = 388"), gap="procedure") | {
        "error": {"student_did": "subtracted 42 from 420 and got 388", "actually_gives": "420 - 42 is 378",
                  "asked_for": "the tablets that remain", "mismatch": "420 - 42 is 378, not 388"}}
    fixed = correct("420 - 42 = 378", "420 - 42 = 378")
    svc, sid, _ = session(store, [slip, fixed], replies=["Check the subtraction.", "And then?"])
    send(svc, sid, "420*0.1 = 42, so 420 - 42 = 388 remain.")
    turn = send(svc, sid, "420 - 42 = 378")
    diagnosed = last(store, sid, "DIAGNOSIS_RESULT")
    assert diagnosed.gap_repaired and diagnosed.mode == "probe" and turn.phase == "teach"
    assert no_support_removed(store, sid)


# ---- the turn cap and the invariant ----


def test_the_turn_cap_offers_a_way_out_and_never_a_fresh_problem(store):
    svc, sid, _ = session(store, [NOTHING])
    turns = [send(svc, sid, "I don't know") for _ in range(2 * MAX_TEACH_TURNS)]
    assert all(t.phase == "teach" for t in turns) and no_support_removed(store, sid)
    offered = [i + 1 for i, t in enumerate(turns) if t.message.endswith(OFFER_EXIT)]
    assert offered == [MAX_TEACH_TURNS, 2 * MAX_TEACH_TURNS]


def test_the_fresh_problem_cannot_start_without_a_resolved_problem(store):
    svc, sid, _ = session(store, [NOTHING])
    with pytest.raises(ApiError) as raised:
        asyncio.run(svc._stress_test(store.get_session(sid), None, resolved=False))
    assert raised.value.status == 500 and store.latest_follow_up(sid) is None


# ---- a non-numeric answer ----

LOGIC = "All mammals breathe air. Whales are mammals. Do whales breathe air? Explain."
LOGIC_SETUP = {"concept_name": "Syllogisms", "steps": ["Whales are mammals.", "All mammals breathe air."],
               "result": "Yes, whales breathe air."}


def test_a_non_numeric_problem_resolves_only_on_an_accepted_conclusion(store):
    concluded = "Whales are mammals and all mammals breathe air, so whales breathe air."
    with_conclusion = diagnosis(("set_up", "correct", "Whales are mammals and all mammals breathe air"),
                                ("interpret", "correct", "so whales breathe air"), gap=None)
    no_conclusion = diagnosis(("set_up", "correct", "Whales are mammals"), gap=None)
    model = ScriptedModel([no_conclusion, with_conclusion], replies=["And so?"], setup=LOGIC_SETUP,
                          follow_ups=[COOKIES])
    svc = SessionService(AgentTutor(store, model.model, FakeVerifier(APPROVE, follow_up_checks=[FOLLOW_UP_OK]).model),
                         store, tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=LOGIC, student_id=MARIA_ID))).session_id
    assert send(svc, sid, "Whales are mammals.").phase == "teach"  # no error found, but no conclusion yet
    assert send(svc, sid, concluded).phase == "stress_test"


def test_only_steps_that_feed_the_answer_are_required():
    """A side calculation nothing uses afterwards is not a target; step numbers are not values."""
    from app.session.schema import Solution
    from app.tutor.evidence import numeric_values
    from app.tutor.resolution import required_targets

    solution = Solution(result="Room A: 215.4 tablets, Room B: 195 tablets", steps=[
        "1. 10% of 420 = 42 damaged", "2. 420 - 42 = 378 remain", "3. 378 × 3/7 = 162 and 378 × 4/7 = 216",
        "4. 162 × 1.2 = 194.4", "5. Room B: 15% of 216 = 32.4 replaced one-for-one, so Room B stays 216",
        "6. 5% of 420 = 21", "7. 194.4 + 21 = 215.4", "8. 216 - 21 = 195"])
    targets = [t.value for t in required_targets(solution, set(numeric_values(PROBLEM)))]
    assert 32.4 not in targets and 7.0 not in targets
    assert targets == [42.0, 378.0, 216.0, 194.4, 216.0, 21.0, 215.4, 195.0]
