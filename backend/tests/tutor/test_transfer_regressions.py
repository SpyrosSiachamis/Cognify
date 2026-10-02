"""Regressions from the live books -> cookies session: a correct, independent fresh-problem answer was marked
NOT YET, and the chain of state and context bugs behind it.

The real SessionService and AgentTutor run here; only the model outputs are scripted (ScriptedModel for the
set-up, reasoning, teaching and follow-up steps, FakeVerifier for the checks), so every result below is decided
by the production code paths.
"""

import asyncio
import json

import pytest

from app.history.schema import ConceptState
from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest, VerdictTurn
from app.tutor.agent import AgentTutor, choose_mode
from app.tutor.reasoning import apply_rules
from app.tutor.repair import assess_repair
from app.tutor.schema import PriorDiagnosis, ReasoningDraft, ReasoningInput, Step
from app.user.errors import ApiError
from app.user.service import MAX_HINTS_FOR_VERIFIED, SessionService
from app.verification.agent import demonstrated_answers

from .fakes import APPROVE, FOLLOW_UP_OK, STUDENT_OK, FakeVerifier, ScriptedModel, diagnosis

BOOKS = ("A box contains 36 books. 12 books are removed. The remaining books are placed equally on 6 shelves. "
         "How many books are on each shelf?")
BOOKS_SETUP = {"concept_name": "Division of whole numbers", "result": "4 books",
               "steps": ["36 - 12 = 24 books remain.", "24 ÷ 6 = 4.", "4 books on each shelf."]}
COOKIES = {
    "problem": "A baker has 50 cookies to pack into boxes. She packs 14 cookies into a gift box for a friend. The rest "
               "are placed equally into 4 containers for a bake sale. How many cookies are in each container?",
    "concept_invariant": "Subtract the part removed, then share the rest equally.",
    "target_gap": "procedure", "target_step": "compute", "perturbation": "context", "difficulty": "medium",
    "hidden_rubric": ["50 - 14 = 36 cookies remain", "36 ÷ 4 = 9", "9 cookies in each container"],
}

WORKED_EXAMPLE = "Try a simpler one: 10 ÷ 2 = ___. Then 24 ÷ 6?"
TABLE = "Total books: 36 | Removed: 12 | Left: ? | Shelves: 6. What goes in 'left'?"
FIRST = ("There are 36 books and 12 are removed, so 36 - 12 = 24 books remain. Then I divide the 24 books equally "
         "among 6 shelves: 24 ÷ 6 = 5. So there are 5 books on each shelf.")
LEAST_SURE = "I'm least sure about the division step. I thought 24 divided by 6 was 5."
WORKED = "10 ÷ 2 = 5, so 24 ÷ 6 = 4."
# The student's answers once the turn count no longer ends teaching: only work that resolves the problem moves on.
EXAMPLE_ANSWER = "10 ÷ 2 = 5."
TABLE_ANSWER = "24 are left, and 24 ÷ 6 = 4, so 4 books on each shelf."
SOLVED_TEXT = "36 - 12 = 24 and 24 ÷ 6 = 4, so 4 books."
FRESH_ANSWER = ("There are 50 cookies and 14 are packed into the gift box, so 50 - 14 = 36 cookies remain. Then I divide "
                "36 equally among 4 containers: 36 ÷ 4 = 9. So there are 9 cookies in each container.")

ERROR = {"student_did": "divided 24 by 6 and got 5", "actually_gives": "5 is not 24 ÷ 6",
         "asked_for": "24 ÷ 6 = 4", "mismatch": "24 ÷ 6 is 4, not 5"}
REJECT = {"mode": "reply_check", "approved": False, "reason": "method_drift", "note": "Does not perform the method."}


def proc(*steps, gap="procedure", **extra) -> dict:
    """A scripted reasoning output; a wrong step carries its error, like the real rules require."""
    out = diagnosis(*steps, gap=gap)
    if any(s[1] == "wrong" for s in steps):
        out["error"] = ERROR
    return out | extra


WRONG_DIVISION = proc(("compute", "correct", "36 - 12 = 24 books remain"), ("compute", "wrong", "24 ÷ 6 = 5"))
STILL_WRONG = proc(("compute", "wrong", "24 divided by 6 was 5"))
# Turn 3: the live session's "10 ÷ 2 = 5, so 24 ÷ 6 = 4." now resolves the problem (24 and 4 demonstrated), so the
# chain below has the student answer only the worked example, and the tutor keeps teaching (with a table). Scripts
# here must satisfy the real rules (a gap shows at its step), or the reasoning step retries and the scripted model
# would serve the next turn's output; each test checks there was no retry.
EXAMPLE_ONLY = proc(("compute", "correct", "10 ÷ 2 = 5"), gap="procedure", response_to="other_problem")
# The answer to the table that finishes the problem: the division and what it counts (resolves it; no reply follows).
TABLE_SOLVED = proc(("compute", "correct", "24 ÷ 6 = 4"), ("interpret", "correct", "4 books on each shelf"), gap=None,
                    response_to="tutor_question")
# The whole chain worked: every required step and the final value demonstrated, so the fresh problem follows.
SOLVED = proc(("compute", "correct", "36 - 12 = 24"), ("compute", "correct", "24 ÷ 6 = 4"), gap=None)
# The same answer read as a repair: the procedure gap is gone, the answer just needs interpreting.
REPAIRED = proc(("compute", "correct", "24 ÷ 6 = 4"), ("interpret", "missing", None), gap="representation")
# "24" to "how many books are left?", read the way the live model read it: as a final answer with a new gap.
BOOKS_LEFT = proc(("compute", "correct", "24"), ("interpret", "missing", None), ("set_up", "missing", None),
                  gap="representation", response_to="tutor_question")


def rig(store, diagnoses, replies, verifier_results, student_check=STUDENT_OK, raise_on=None, setup=BOOKS_SETUP,
        follow_ups=(COOKIES,), student_checks=None, problem=BOOKS):
    model = ScriptedModel(diagnoses, replies=replies, setup=setup, follow_ups=list(follow_ups), raise_on=raise_on)
    verifier = FakeVerifier(*verifier_results, follow_up_checks=[FOLLOW_UP_OK],
                            student_checks=student_checks or [student_check])
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=problem, student_id=MARIA_ID))).session_id
    return svc, sid, model, verifier


def send(svc, sid, text):
    return asyncio.run(svc.attempt(sid, text))


def concept_id(store):
    return store.get_or_create_concept(BOOKS_SETUP["concept_name"]).id


def verified_before(store):
    store.upsert_concept_state(ConceptState(student_id=MARIA_ID, concept_id=concept_id(store), state="verified",
                                            evidence=["Verified in an earlier session."]))


# ---- A: the reported chain ----


def test_a_cookie_transfer_after_fallback_worked_example_and_table_is_verified(store):
    """Fallback -> approved worked example -> approved table -> fresh problem -> correct, own work, strong.
    The fallback is no help, so two hints were used: within the F16 limit, VERIFIED (before the fix: 3, NOT YET)."""
    verified_before(store)
    svc, sid, model, verifier = rig(
        store,
        [WRONG_DIVISION, STILL_WRONG, EXAMPLE_ONLY, TABLE_SOLVED],
        # Turn 1's rejected drafts use two reply slots (the third retry repeats the second's input, which the scripted
        # model does not count again); the worked example and the table follow.
        replies=["(rejected draft 1)", "(rejected draft 2)", WORKED_EXAMPLE, TABLE, "unused"],
        verifier_results=[REJECT, REJECT, REJECT, APPROVE, APPROVE, APPROVE],
    )
    t1 = send(svc, sid, FIRST)
    assert t1.reply_check.outcome == "verifier_rejected" and t1.method is None  # the fallback: no method shown
    t2 = send(svc, sid, LEAST_SURE)
    assert t2.hints_used == 0 and t2.reply_check.outcome == "approved" and t2.message == WORKED_EXAMPLE
    t3 = send(svc, sid, EXAMPLE_ANSWER)
    assert t3.hints_used == 1 and t3.message == TABLE
    fresh = send(svc, sid, TABLE_ANSWER)  # resolved: the fresh problem replaces this turn's reply
    assert model.reasoning_inputs[-1]["tutor_message"] == TABLE  # read as the answer to the table
    assert fresh.phase == "stress_test" and fresh.hints_used == 2
    verdict = send(svc, sid, FRESH_ANSWER)
    assert isinstance(verdict, VerdictTurn)
    assert verifier.student_inputs[-1]["student_text"] == FRESH_ANSWER
    v = verdict.verdict
    assert (v.result, v.independent, v.remaining_gap) == ("VERIFIED", True, None)
    assert (v.changes.concept.before, v.changes.concept.after) == ("verified", "verified")
    assert store.get_concept_state(MARIA_ID, concept_id(store)).state == "verified"  # no downgrade
    assert model.reasoning_calls == 4  # one per teaching turn: no rule rejected a scripted diagnosis


def test_a_when_the_repair_is_recognised_the_fresh_problem_comes_with_one_hint(store):
    svc, sid, model, _ = rig(store, [WRONG_DIVISION, STILL_WRONG, REPAIRED], replies=["a", "b", "c"],
                             verifier_results=[REJECT, REJECT, REJECT, APPROVE])
    send(svc, sid, FIRST)
    send(svc, sid, LEAST_SURE)
    fresh = send(svc, sid, WORKED)
    assert fresh.phase == "stress_test" and fresh.hints_used == 1  # only the worked example helped
    assert send(svc, sid, FRESH_ANSWER).verdict.result == "VERIFIED"
    assert model.reasoning_calls == 3


def test_a_the_verdict_credits_the_last_delivered_move_of_this_cycle(store):
    svc, sid, _, _ = rig(store, [WRONG_DIVISION, STILL_WRONG, EXAMPLE_ONLY, TABLE_SOLVED],
                         replies=["a", "b", "c", "d"], verifier_results=[REJECT, REJECT, REJECT, APPROVE])
    for text in (FIRST, LEAST_SURE, EXAMPLE_ANSWER, TABLE_ANSWER):
        send(svc, sid, text)
    decisions = store.list_strategy_decisions(sid)
    assert len(decisions) == 2  # the worked example and the table; the fallback and the resolved turn taught nothing
    verdict = send(svc, sid, FRESH_ANSWER).verdict
    assert verdict.changes.strategy.method == decisions[-1].method
    after, before = verdict.changes.strategy.after, verdict.changes.strategy.before
    assert (after.uses - before.uses, after.independent_successes - before.independent_successes) == (1, 1)


# ---- F: what counts as a hint ----


def test_f_three_fallback_turns_use_no_hint(store):
    svc, sid, _, _ = rig(store, [WRONG_DIVISION] * 3 + [SOLVED], replies=["x"], verifier_results=[REJECT])
    for text in (FIRST, "Again 24 ÷ 6 = 5.", "Still 24 ÷ 6 = 5.", SOLVED_TEXT):  # three fallbacks, then solved
        turn = send(svc, sid, text)
    assert turn.phase == "stress_test" and turn.hints_used == 0
    assert store.list_strategy_decisions(sid) == []  # no method was delivered, none is credited
    assert send(svc, sid, FRESH_ANSWER).verdict.result == "VERIFIED"


def test_f_three_approved_teaching_moves_exceed_the_limit(store):
    """F16 is unchanged: help that reached the student counts, and too much of it is NOT YET even when right."""
    verified_before(store)
    svc, sid, _, _ = rig(store, [WRONG_DIVISION] * 3 + [SOLVED], replies=["m1", "m2", "m3", "m4"],
                         verifier_results=[APPROVE])
    for text in (FIRST, "Again 24 ÷ 6 = 5.", "Still 24 ÷ 6 = 5.", SOLVED_TEXT):  # three moves, then solved
        turn = send(svc, sid, text)
    assert turn.phase == "stress_test" and turn.hints_used == 3 > MAX_HINTS_FOR_VERIFIED
    v = send(svc, sid, FRESH_ANSWER).verdict
    assert (v.result, v.independent) == ("NOT YET", False)
    outcome = [o for o in store._outcomes if o.session_id == sid][-1]
    assert outcome.not_yet_reason == "hint_limit"
    # Solved correctly on their own: help dependence, not regression. A verified concept is not downgraded.
    assert (v.changes.concept.before, v.changes.concept.after) == ("verified", "verified")


def test_f_a_probe_is_not_a_hint(store):
    nothing = diagnosis(("choose_method", "missing", None), gap=None, confidence="low", evidence="insufficient")
    svc, sid, model, _ = rig(store, [nothing, WRONG_DIVISION], replies=["What did you try first?", "m"],
                             verifier_results=[APPROVE])
    probe = send(svc, sid, "I don't know.")
    assert model.teaching_inputs[0]["mode"] == "probe" and probe.method is None
    assert send(svc, sid, FIRST).hints_used == 0


def test_f_an_acknowledgement_and_a_blank_answer_are_not_hints(store):
    svc, sid, _, _ = rig(store, [WRONG_DIVISION, WRONG_DIVISION], replies=["m"], verifier_results=[APPROVE])
    send(svc, sid, FIRST)  # an approved teaching move: one hint owed for the next answer
    blank = send(svc, sid, "   ")
    assert blank.reply_check.outcome == "fixed_reply" and blank.hints_used == 0
    assert send(svc, sid, LEAST_SURE).hints_used == 1  # the owed hint, counted once, not one for the blank turn


def test_f_a_failed_turn_keeps_the_owed_hint_and_adds_none(store):
    svc, sid, model, _ = rig(store, [WRONG_DIVISION, WRONG_DIVISION, WRONG_DIVISION], replies=["m"],
                             verifier_results=[APPROVE])
    send(svc, sid, FIRST)
    model.raise_on = "BREAK"
    failed = send(svc, sid, "BREAK the reasoning call")
    assert failed.reply_check.outcome == "turn_failed" and failed.hints_used == 0
    model.raise_on = None
    assert send(svc, sid, LEAST_SURE).hints_used == 1


def test_f_the_reply_replaced_by_the_fresh_problem_is_not_credited(store):
    svc, sid, _, _ = rig(store, [WRONG_DIVISION] * 3 + [SOLVED], replies=["m1", "m2", "m3", "m4"],
                         verifier_results=[APPROVE])
    for text in (FIRST, "Again.", "Still 24 ÷ 6 = 5.", SOLVED_TEXT):
        send(svc, sid, text)
    assert len(store.list_strategy_decisions(sid)) == 3  # the resolving turn's reply is the fresh problem, no move
    assert store.get_session(sid).last_reply_taught is False


# ---- B and C: intermediate answers do not contaminate the diagnosis ----


def test_b_books_left_answer_is_a_correct_intermediate_step_not_a_final_answer(store):
    svc, sid, model, _ = rig(store, [WRONG_DIVISION, BOOKS_LEFT], replies=["How many books are left?", "next"],
                             verifier_results=[APPROVE])
    send(svc, sid, FIRST)
    turn = send(svc, sid, "24")
    reasoning_input = model.reasoning_inputs[-1]
    assert reasoning_input["tutor_message"] == "How many books are left?"
    assert turn.phase == "teach"  # not the skip-to-fresh-problem rule, not an acknowledgement
    assert turn.diagnosis.main_gap == "procedure"  # the gap being taught, not a new representation gap
    assert [(s.role, s.status) for s in turn.diagnosis.steps] == [("compute", "correct")]  # unasked steps dropped
    assert not any(s.status == "wrong" for s in turn.diagnosis.steps)
    assert store.list_attempts(sid)[-1].response_to == "tutor_question"


def test_b_24_divided_by_6_answer_to_a_subquestion_is_not_the_final_answer():
    """Tutor: "What is 24 ÷ 6?" Student: "4". A correct bare sub-answer is not the whole solution and, with no
    working shown, not yet a repair either."""
    prior = PriorDiagnosis(steps=[Step(role="compute", status="wrong", quote="24 ÷ 6 = 5")], main_gap="procedure")
    draft = ReasoningDraft.model_validate(proc(("compute", "correct", "4"), ("interpret", "missing", None),
                                               gap=None, response_to="tutor_question"))
    d = apply_rules(draft, "4", recheck=False, has_tutor_message=True)
    assert d.response_to == "tutor_question" and [(s.role, s.status) for s in d.steps] == [("compute", "correct")]
    assert choose_mode(d, "procedure", assess_repair(prior, d).repaired) == "teach"  # never acknowledged as solved
    assert not assess_repair(prior, d).repaired


def test_b_a_worked_subanswer_at_the_gap_step_is_a_repair_but_not_at_another_step():
    prior = PriorDiagnosis(steps=[Step(role="compute", status="wrong", quote="24 ÷ 6 = 5")], main_gap="procedure")
    at_gap = ReasoningDraft.model_validate(proc(("compute", "correct", "24 ÷ 6 = 4"), gap=None, response_to="tutor_question"))
    elsewhere = ReasoningDraft.model_validate(proc(("set_up", "correct", "36 - 12 = 24 books"), gap=None,
                                                   response_to="tutor_question"))
    assert assess_repair(prior, apply_rules(at_gap, "24 ÷ 6 = 4", recheck=False, has_tutor_message=True)).repaired
    assert not assess_repair(prior, apply_rules(elsewhere, "36 - 12 = 24 books", recheck=False,
                                                has_tutor_message=True)).repaired


def test_c_a_worked_example_answer_is_not_evidence_about_the_original_problem(store):
    mislabelled = proc(("compute", "wrong", "5"), gap="representation", response_to="other_problem")
    svc, sid, _, _ = rig(store, [WRONG_DIVISION, mislabelled], replies=["Try: 10 ÷ 2 = ___", "next"],
                         verifier_results=[APPROVE])
    send(svc, sid, FIRST)
    turn = send(svc, sid, "5")
    assert turn.phase == "teach" and turn.diagnosis.main_gap == "procedure"  # carried; no representation drift
    assert not any(s.status == "wrong" for s in turn.diagnosis.steps)  # "5" is not judged against the books problem


@pytest.mark.parametrize("kind", ["clarification", "acknowledgement"])
def test_c_a_question_back_or_an_ok_keeps_the_gap_being_taught(store, kind):
    guess = proc(("interpret", "wrong", "wdym"), gap="representation", response_to=kind)
    svc, sid, _, _ = rig(store, [WRONG_DIVISION, guess], replies=["m", "n"], verifier_results=[APPROVE])
    send(svc, sid, FIRST)
    turn = send(svc, sid, "wdym")
    assert turn.phase == "teach" and turn.diagnosis.main_gap == "procedure"


def test_without_a_tutor_message_the_answer_is_always_work_on_the_problem():
    draft = ReasoningDraft.model_validate(proc(("compute", "correct", "24 ÷ 6 = 4"), gap=None, response_to="other_problem"))
    assert apply_rules(draft, "24 ÷ 6 = 4", recheck=False, has_tutor_message=False).response_to == "original_problem"
    assert "tutor_message" not in ReasoningInput(problem="p", attempt="a").prompt()  # same payload as before


def test_a_partial_answer_with_no_gap_being_taught_does_not_skip_to_another_fresh_problem(store):
    """A correct first thought goes straight to the fresh problem (no gap ever taught). After a NOT YET, a correct
    answer to part of the problem is not the whole solution: it must not send the student to a new fresh problem."""
    correct = proc(("compute", "correct", "36 - 12 = 24"), ("compute", "correct", "24 ÷ 6 = 4"), gap=None)
    part = proc(("compute", "correct", "36 - 12 = 24"), gap=None, response_to="tutor_question")
    # After the NOT YET the cookies problem is the one being repaired, so the set-up solves it (not the books again).
    svc, sid, model, _ = rig(store, [correct, part], replies=["What would you try next?"], verifier_results=[APPROVE],
                             student_check={**STUDENT_OK, "correct": False}, setup=[BOOKS_SETUP, COOKIES_SETUP])
    assert send(svc, sid, "36 - 12 = 24 and 24 ÷ 6 = 4, so 4 books.").phase == "stress_test"
    assert send(svc, sid, "36 ÷ 4 = 8").verdict.result == "NOT YET"
    turn = send(svc, sid, "36 - 12 = 24")
    assert turn.phase == "teach"  # a probe, not a second fresh problem
    assert model.reasoning_calls == 2


# ---- H: after a NOT YET the failed fresh problem is the problem being repaired ----

COOKIES_SETUP = {"concept_name": "Division of whole numbers", "result": "9 cookies",
                 "steps": ["50 - 14 = 36 cookies remain.", "36 ÷ 4 = 9.", "9 cookies in each container."]}
COOKIES_SOLVED = proc(("compute", "correct", "50 - 14 = 36"), ("compute", "correct", "36 ÷ 4 = 9"), gap=None)

APPLES = {
    "problem": "A farmer has 45 apples in a basket. He sells 19 apples at the market. How many apples are left in "
               "the basket?",
    "concept_invariant": "Subtract the part removed to find what remains.",
    "target_gap": "procedure", "target_step": "compute", "perturbation": "context", "difficulty": "easy",
    "hidden_rubric": ["45 - 19 = 26", "26 apples are left"],
}
APPLES_SETUP = {"concept_name": "Subtraction of whole numbers", "result": "26 apples",
                "steps": ["45 - 19 = 26.", "26 apples are left."]}
PEARS = {**COOKIES, "problem": "A shop has 60 pears. It sells 15 and packs the rest equally into 5 crates. "
                               "How many pears are in each crate?"}
WRONG = {**STUDENT_OK, "correct": False, "note": "'45 - 19 = 36' does not match the expected result of 26."}
SOLVED_AT_ONCE = proc(("compute", "correct", "36 - 12 = 24"), ("compute", "correct", "24 ÷ 6 = 4"), gap=None)
APPLES_REPAIRED = proc(("compute", "correct", "45-19=26"), ("interpret", "correct", "26 apples are left"), gap=None)
NOTHING = diagnosis(("choose_method", "missing", None), gap=None, confidence="low", evidence="insufficient")


def apples_not_yet(store, repair_diagnoses, replies=("unused",)):
    """Books solved at once -> the apples fresh problem -> "45 - 19 = 36" -> a first NOT YET (the reported session)."""
    svc, sid, model, verifier = rig(
        store, [SOLVED_AT_ONCE, *repair_diagnoses], replies=list(replies), verifier_results=[APPROVE],
        setup=[BOOKS_SETUP, APPLES_SETUP], follow_ups=(APPLES, PEARS), student_checks=[WRONG, STUDENT_OK],
    )
    assert send(svc, sid, "36 - 12 = 24 and 24 ÷ 6 = 4, so 4 books.").follow_up.problem == APPLES["problem"]
    verdict = send(svc, sid, "45 - 19 = 36, so 36 apples are left.")
    assert (verdict.verdict.result, verdict.session_over) == ("NOT YET", False)
    return svc, sid, model, verifier


def test_h_after_not_yet_the_repair_is_diagnosed_against_the_practice_problem(store):
    svc, sid, model, _ = apples_not_yet(store, [APPLES_REPAIRED])
    practice = store.get_session(sid).active_practice_problem
    assert practice is not None and practice.text == APPLES["problem"]
    assert practice.follow_up_id == store.latest_follow_up(sid).id
    assert practice.solution.result == "26 apples"  # solved by the set-up step, not taken from the rubric
    assert model.setup_inputs[-1]["problem"] == APPLES["problem"]
    send(svc, sid, "45-19=26, so 26 apples are left")
    reasoning_input = model.reasoning_inputs[-1]
    assert reasoning_input["problem"] == APPLES["problem"] and reasoning_input["final_answer"] == "26 apples"
    assert "books" not in json.dumps(reasoning_input)


def test_h_a_correct_repair_of_the_practice_problem_moves_on_without_asking_about_the_books(store):
    svc, sid, model, verifier = apples_not_yet(store, [APPLES_REPAIRED])
    turn = send(svc, sid, "45-19=26, so 26 apples are left")
    assert model.reasoning_calls == 2  # one per teaching turn: no rule rejected the scripted repair
    assert turn.phase == "stress_test"  # the existing next state: no probe, no question about the books
    assert model.teaching_inputs == []  # no reply was written for this turn: the fresh problem replaces it
    assert "books" not in turn.message
    assert turn.hints_used == 0  # the verdict was not a teaching move


def test_h_solving_the_practice_problem_is_not_verified_transfer(store):
    svc, sid, model, verifier = apples_not_yet(store, [APPLES_REPAIRED])
    turn = send(svc, sid, "45-19=26, so 26 apples are left")
    # Freshness: a new problem, never the apples one the student was already told was wrong.
    assert turn.follow_up.problem == PEARS["problem"]
    assert len(verifier.student_inputs) == 1  # the repair was not judged
    outcomes = [o.result for o in store._outcomes if o.session_id == sid]
    assert outcomes == ["NOT YET"]  # nothing VERIFIED was recorded for the apples
    session = store.get_session(sid)
    assert session.active_practice_problem is None and session.phase == "stress_test"
    # The follow-up stays anchored to the session's own problem.
    assert model.follow_up_inputs[-1]["problem"] == BOOKS
    verdict = send(svc, sid, "60 - 15 = 45, and 45 ÷ 5 = 9, so 9 pears in each crate.")
    assert verdict.verdict.result == "VERIFIED"
    assert verifier.student_inputs[-1]["follow_up"] == PEARS["problem"]


def test_h_the_original_problem_stays_the_sessions_problem(store):
    svc, sid, model, _ = apples_not_yet(store, [NOTHING])
    session = store.get_session(sid)
    assert store.get_problem(session.problem_id).text == BOOKS
    assert session.hidden_solution.result == "4 books"
    outcome = [o for o in store._outcomes if o.session_id == sid][-1]
    assert outcome.concept_id == concept_id(store)  # the books concept, not one named for the apples
    assert asyncio.run(svc.exit(sid)).solution.result == "4 books"  # exit reveals the original problem's solution


def test_h_a_probe_on_the_practice_problem_stays_the_context(store):
    """The reported follow-on: after a probe, "you gave me an apples problem" lost all context."""
    probe = "What did you try first with the 45 apples?"
    svc, sid, model, _ = apples_not_yet(store, [NOTHING, NOTHING], replies=[probe, "next"])
    asked = send(svc, sid, "I don't know.")
    assert model.teaching_inputs[-1]["mode"] == "probe" and model.teaching_inputs[-1]["problem"] == APPLES["problem"]
    assert asked.message == probe and asked.method is None
    after = send(svc, sid, "you gave me an apples problem")
    assert model.reasoning_inputs[-1]["tutor_message"] == probe  # read as an answer to the probe
    assert model.reasoning_inputs[-1]["problem"] == APPLES["problem"]
    assert after.hints_used == 0  # the probe was no hint


def test_h_context_and_hints_have_separate_lifecycles(store):
    """Context is the reply the student saw; a hint is only an approved teaching move that reached them."""
    svc, sid, model, _ = rig(store, [NOTHING, WRONG_DIVISION, WRONG_DIVISION, WRONG_DIVISION],
                             replies=["What did you try first?", "m1", "unused"],
                             verifier_results=[APPROVE, APPROVE, REJECT])
    probe = send(svc, sid, "I don't know.")  # a probe: context, no hint
    taught = send(svc, sid, FIRST)  # an approved teaching move: context, and a hint owed
    assert model.reasoning_inputs[-1]["tutor_message"] == probe.message and taught.hints_used == 0
    fallback = send(svc, sid, LEAST_SURE)  # every draft rejected: the safe fallback is context, not a hint
    assert model.reasoning_inputs[-1]["tutor_message"] == taught.message and fallback.hints_used == 1
    assert fallback.reply_check.outcome == "verifier_rejected"
    send(svc, sid, "24 ÷ 6 = 5, I think.")
    assert model.reasoning_inputs[-1]["tutor_message"] == fallback.message
    assert store.get_session(sid).hints_used == 1  # the fallback added none


# ---- D and E: the answer-leak guard ----


DERIVED = proc(("compute", "correct", "24 ÷ 6 = 4"), ("interpret", "missing", None), gap="representation")
# On the books problem "24 ÷ 6 = 4" now resolves the problem (24 and 4 demonstrated) and the fresh problem follows,
# so the leak guard is exercised on the same problem one step longer: the division shows the final 4 while the
# 41 - 5 = 36 step is still open, and the tutor keeps replying.
LONGER = ("A box contains 41 books. 5 damaged books are thrown away, then 12 books are removed. The remaining books "
          "are placed equally on 6 shelves. How many books are on each shelf?")
LONGER_SETUP = {"concept_name": "Division of whole numbers", "result": "4 books",
                "steps": ["41 - 5 = 36 books are left.", "36 - 12 = 24 books remain.", "24 ÷ 6 = 4.",
                          "4 books on each shelf."]}


def test_d_repeating_the_students_own_result_is_not_a_leak(store):
    derived = DERIVED
    svc, sid, model, verifier = rig(store, [derived], replies=["Exactly — 24 ÷ 6 = 4. What does that 4 tell you?"],
                                verifier_results=[APPROVE], problem=LONGER, setup=LONGER_SETUP)
    turn = send(svc, sid, "24 ÷ 6 = 4")
    assert turn.reply_check.outcome == "approved" and "24 ÷ 6 = 4" in turn.message
    assert verifier.inputs[0]["student_demonstrated"] == ["24 ÷ 6 = 4"]  # the model check is told what they derived
    assert model.reasoning_calls == 1


def test_d_a_result_derived_in_an_earlier_turn_may_be_confirmed(store):
    stuck = proc(("interpret", "missing", "not sure what it means"), gap="representation")
    svc, sid, model, verifier = rig(store, [DERIVED, stuck],
                                    replies=["So what does it mean?", "Yes, 24 ÷ 6 = 4. What is that 4 counting?"],
                                    verifier_results=[APPROVE], problem=LONGER, setup=LONGER_SETUP)
    send(svc, sid, "24 ÷ 6 = 4")
    turn = send(svc, sid, "I'm not sure what it means.")
    assert turn.reply_check.outcome == "approved" and "24 ÷ 6 = 4" in turn.message
    assert model.reasoning_calls == 2


def test_d_the_unit_the_student_never_stated_is_still_theirs_to_find(store):
    """Deriving "24 ÷ 6 = 4" shows the 4, not that it is 4 books per shelf: handing over "4 books" is a leak."""
    stuck = proc(("interpret", "missing", "not sure what it means"), gap="representation")
    svc, sid, _, _ = rig(store, [DERIVED, stuck], replies=["So what does it mean?", "You found 4 books per shelf."],
                         verifier_results=[APPROVE], problem=LONGER, setup=LONGER_SETUP)
    send(svc, sid, "24 ÷ 6 = 4")
    turn = send(svc, sid, "I'm not sure what it means.")
    assert turn.reply_check.outcome == "verifier_rejected" and "4 books" not in turn.message


def test_e_stating_an_answer_the_student_has_not_derived_is_a_leak(store):
    open_question = proc(("compute", "missing", "24 ÷ 6 = ?"), gap="procedure")
    svc, sid, _, verifier = rig(store, [open_question], replies=["24 ÷ 6 = 4."], verifier_results=[APPROVE])
    turn = send(svc, sid, "24 ÷ 6 = ?")
    assert turn.reply_check.outcome == "verifier_rejected" and "4." not in turn.message  # safe fallback
    assert verifier.inputs == []  # the code check caught it before the model check
    drafts = store.list_reply_drafts(sid)
    assert [d.reason for d in drafts] == ["answer_leak"] * 3


@pytest.mark.parametrize("quote", ["is it 4?", "4", "24 ÷ 6 = 5", "There are 6 shelves and 4 is a guess"])
def test_e_a_guess_a_wrong_result_or_an_unworked_value_is_not_demonstrated(quote):
    assert demonstrated_answers([("compute", "correct", quote)], ["4 books", "4"], BOOKS) == ([], [])


def test_e_a_quantity_given_in_the_problem_is_never_demonstrated():
    assert demonstrated_answers([("compute", "correct", "36 - 30 = 6")], ["6"], BOOKS) == ([], [])


# ---- G: evaluation failures never change the learner state ----


def test_g_a_failed_judgement_records_nothing_and_keeps_a_verified_concept(store):
    verified_before(store)
    svc, sid, model, verifier = rig(store, [WRONG_DIVISION] * 3 + [SOLVED], replies=["m"], verifier_results=[REJECT])
    for text in (FIRST, "Again.", "Still 24 ÷ 6 = 5.", SOLVED_TEXT):
        send(svc, sid, text)
    verifier.student_checks = [{"mode": "student_check"}]  # an invalid check: the verifier call fails
    with pytest.raises(ApiError) as failed:
        send(svc, sid, FRESH_ANSWER)
    assert failed.value.status == 503
    assert [o for o in store._outcomes if o.session_id == sid] == []
    assert store.get_concept_state(MARIA_ID, concept_id(store)).state == "verified"
    assert [a.phase for a in store.list_attempts(sid)].count("stress_test") == 0  # nothing half-written


def test_g_a_genuinely_incorrect_answer_still_downgrades(store):
    verified_before(store)
    svc, sid, _, _ = rig(store, [WRONG_DIVISION] * 3 + [SOLVED], replies=["m"], verifier_results=[REJECT],
                         student_check={**STUDENT_OK, "correct": False, "reasoning_quality": "weak"})
    for text in (FIRST, "Again.", "Still 24 ÷ 6 = 5.", SOLVED_TEXT):
        send(svc, sid, text)
    v = send(svc, sid, "36 ÷ 4 = 8").verdict
    assert v.result == "NOT YET" and (v.changes.concept.before, v.changes.concept.after) == ("verified", "fragile")
    assert [o for o in store._outcomes if o.session_id == sid][-1].not_yet_reason == "incorrect"


# ---- telemetry ----


def test_every_draft_is_kept_with_its_outcome_and_reason(store):
    svc, sid, _, _ = rig(store, [WRONG_DIVISION], replies=["m"], verifier_results=[REJECT, REJECT, APPROVE])
    turn = send(svc, sid, FIRST)
    assert turn.reply_check.outcome == "approved"
    assert [(d.position, d.outcome, d.reason) for d in store.list_reply_drafts(sid)] == [
        (0, "verifier_rejected", "method_drift"), (1, "verifier_rejected", "method_drift"), (2, "approved", None)]


def test_a_teaching_step_failure_is_not_reported_as_a_verifier_rejection(store):
    # An empty reply fails the teaching step's output validation: the gateway reports invalid_output.
    svc, sid, model, verifier = rig(store, [WRONG_DIVISION], replies=[""], verifier_results=[APPROVE])
    turn = send(svc, sid, FIRST)
    assert turn.reply_check.outcome == "teaching_failed" and not turn.reply_check.approved
    assert "verifier rejected" not in turn.reply_check.summary
    assert verifier.inputs == []
    assert [d.outcome for d in store.list_reply_drafts(sid)] == ["teaching_failed"]


# ---- review follow-ups: credit across cycles, the paired prior, and the leak-guard gates ----


def test_the_verdict_credits_the_last_delivered_move_not_the_first(store):
    # Still the wrong division (so the procedure gap is not repaired), now also read as a representation gap.
    representation = proc(("compute", "wrong", "24 ÷ 6 = 5"), ("interpret", "wrong", "so 5 books"),
                          gap="representation")
    svc, sid, _, _ = rig(store, [WRONG_DIVISION, representation, representation, SOLVED],
                         replies=["a", "b", "c", "d"], verifier_results=[APPROVE])
    for text in (FIRST, "24 ÷ 6 = 5, so 5 books.", "Still 24 ÷ 6 = 5, so 5 books.", SOLVED_TEXT):
        send(svc, sid, text)
    decisions = store.list_strategy_decisions(sid)
    assert (decisions[0].gap_type, decisions[-1].gap_type) == ("procedure", "representation")
    strategy = send(svc, sid, FRESH_ANSWER).verdict.changes.strategy
    assert (strategy.gap, strategy.method) == ("representation", decisions[-1].method)


def test_a_cycle_that_delivered_nothing_credits_no_method_from_an_earlier_cycle(store):
    """Cycle 1 delivers one move and ends NOT YET (it is credited then). Cycle 2 is all fallbacks and ends VERIFIED:
    no method is credited for that success."""
    # Each cycle ends on a resolving answer; cycle 2 repairs the cookies problem, which the set-up solves.
    svc, sid, model, verifier = rig(store, [WRONG_DIVISION] * 3 + [SOLVED] + [WRONG_DIVISION] * 3 + [COOKIES_SOLVED],
                                    replies=["m"], verifier_results=[APPROVE] + [REJECT] * 60,
                                    student_check={**STUDENT_OK, "correct": False}, setup=[BOOKS_SETUP, COOKIES_SETUP])
    verifier.student_checks = [{**STUDENT_OK, "correct": False}, STUDENT_OK]
    # A second fresh problem: the first one has been seen, and a repeat is refused.
    model.follow_ups = [COOKIES, {**COOKIES, "problem": "A teacher has 45 pencils. She keeps 5. The rest are shared "
                                  "equally among 8 students. How many pencils does each student get?"}]
    for text in (FIRST, "Again.", "Still 24 ÷ 6 = 5.", SOLVED_TEXT):
        send(svc, sid, text)
    first = send(svc, sid, "36 ÷ 4 = 8").verdict
    assert first.result == "NOT YET" and first.changes.strategy is not None
    credited = (first.changes.strategy.gap, first.changes.strategy.method)
    stats = lambda: {(x.gap_type, x.method): (x.uses, x.independent_successes) for x in store.strategy_stats(MARIA_ID)}
    after_first = stats()[credited]
    assert svc._earlier_correct_steps(store.get_session(sid)) == []  # cycle 1's work is not cycle 2's evidence
    for text in ("Again.", "Still 24 ÷ 6 = 5.", "24 ÷ 6 = 5, I think.", "50 - 14 = 36 and 36 ÷ 4 = 9, so 9 cookies."):
        send(svc, sid, text)
    second = send(svc, sid, FRESH_ANSWER).verdict
    assert second.result == "VERIFIED" and second.changes.strategy is None
    assert stats()[credited] == after_first


def test_a_wrong_answer_to_a_subquestion_keeps_its_own_steps_and_gap_paired(store):
    """The prior for the repair check is the last answer that was work on the problem (here the first one): a later
    correct "24 ÷ 6 = 4" repairs the division gap even though a sub-answer came in between."""
    svc, sid, model, _ = rig(store, [WRONG_DIVISION, BOOKS_LEFT, REPAIRED], replies=["How many books are left?", "next"],
                             verifier_results=[APPROVE])
    send(svc, sid, FIRST)
    send(svc, sid, "24")
    prior = svc._prior(store.get_session(sid))
    assert ("compute", "wrong", "24 ÷ 6 = 5") in [(s.role, s.status, s.quote) for s in prior.steps]
    third = send(svc, sid, "24 ÷ 6 = 4")
    assert third.phase == "stress_test" and third.hints_used == 2 and model.reasoning_calls == 3


def test_a_worded_subanswer_at_a_non_calculation_gap_step_can_repair():
    prior = PriorDiagnosis(steps=[Step(role="interpret", status="missing")], main_gap="representation")
    worded = ReasoningDraft.model_validate(proc(("interpret", "correct", "each shelf gets four of the books"),
                                                gap=None, response_to="tutor_question"))
    bare = ReasoningDraft.model_validate(proc(("interpret", "correct", "four books"), gap=None, response_to="tutor_question"))
    assert assess_repair(prior, apply_rules(worded, "each shelf gets four of the books", recheck=False,
                                            has_tutor_message=True)).repaired
    assert not assess_repair(prior, apply_rules(bare, "four books", recheck=False, has_tutor_message=True)).repaired


@pytest.mark.parametrize(("step", "unlocked"), [
    (("compute", "correct", "4 × 6 = 24"), []),  # 4 is an operand, not the result
    (("set_up", "correct", "24 ÷ 6 = 4"), []),  # not a calculation step
    (("compute", "wrong", "24 ÷ 6 = 4"), []),
    (("compute", "missing", "24 ÷ 6 = 4"), []),
    (("compute", "correct", "The speed is 20 m/s and it is 4"), []),  # "m/s" is not an operation
    (("compute", "correct", "x = -4 so 4"), []),
    (("compute", "correct", "24/6 = 4"), ["4"]),  # compact work counts
    (("interpret", "correct", "24 ÷ 6 = 4 books"), ["4 books", "4"]),  # the unit, only when the student says it
])
def test_the_demonstration_gates(step, unlocked):
    assert demonstrated_answers([step], ["4 books", "4"], BOOKS)[1] == unlocked


def test_a_result_from_an_answer_with_a_wrong_step_is_not_demonstrated(store):
    mixed = proc(("compute", "correct", "24 ÷ 6 = 4"), ("interpret", "wrong", "so 5 books"), gap="representation")
    stuck = proc(("interpret", "missing", "not sure"), gap="representation")
    svc, sid, _, verifier = rig(store, [mixed, stuck], replies=["What does each shelf get?", "24 ÷ 6 = 4."],
                                verifier_results=[APPROVE])
    send(svc, sid, "24 ÷ 6 = 4, so 5 books.")
    turn = send(svc, sid, "I'm not sure.")
    assert turn.reply_check.outcome == "verifier_rejected" and len(verifier.inputs) == 1  # only turn 1 reached it


def test_an_invalid_outcome_writes_nothing(store, monkeypatch):
    """The outcome is built (validated) before the attempt, the check and the verdict are written."""
    import app.user.service as service_module

    svc, sid, _, _ = rig(store, [WRONG_DIVISION] * 3 + [SOLVED], replies=["m"], verifier_results=[REJECT])
    for text in (FIRST, "Again.", "Still 24 ÷ 6 = 5.", SOLVED_TEXT):
        send(svc, sid, text)
    checks_before = len(store._checks)

    def broken(**_):
        raise ValueError("invalid outcome")

    monkeypatch.setattr(service_module.rec, "Outcome", broken)
    with pytest.raises(ValueError):
        send(svc, sid, FRESH_ANSWER)
    session = store.get_session(sid)
    assert "stress_test" not in [a.phase for a in store.list_attempts(sid)]
    assert len(store._checks) == checks_before and [o for o in store._outcomes if o.session_id == sid] == []
    assert (session.phase, session.not_yet_count) == ("stress_test", 0)


def test_a_verifier_failure_is_reported_as_a_verifier_error(store):
    svc, sid, _, _ = rig(store, [WRONG_DIVISION], replies=["m"], verifier_results=[{"mode": "reply_check"}])
    turn = send(svc, sid, FIRST)
    assert turn.reply_check.outcome == "verifier_error" and not turn.reply_check.approved
    assert [d.outcome for d in store.list_reply_drafts(sid)] == ["verifier_error"]
    assert "Traceback" not in turn.reply_check.summary and "invalid_output" not in turn.reply_check.summary


def test_drafts_in_the_wrong_language_are_reported_as_such(store):
    greek = proc(("compute", "wrong", "24 / 6 = 5"), gap="procedure")
    svc, sid, _, verifier = rig(store, [greek], replies=["What is 24 / 6 really?"], verifier_results=[APPROVE])
    turn = send(svc, sid, "Βρήκα 24 / 6 = 5 βιβλία σε κάθε ράφι.")
    assert turn.reply_check.outcome == "wrong_language"
    assert [d.outcome for d in store.list_reply_drafts(sid)] == ["wrong_language"] * 3 and verifier.inputs == []


def test_the_agent_reports_no_method_for_a_fallback(store):
    """TeachResult.method is the method of a move that reached the student; a fallback reached them with none."""
    from .conftest import teach_request

    model = ScriptedModel([WRONG_DIVISION], replies=["m"], setup=BOOKS_SETUP)
    rejected = AgentTutor(store, model.model, FakeVerifier(REJECT).model)
    result, trace = asyncio.run(rejected.teach_with_trace(teach_request(FIRST, problem=BOOKS)))
    assert trace.strategy is not None and trace.fallback  # a method was chosen, but its reply never went out
    assert result.method is None and result.reply_check.outcome == "verifier_rejected"
    approved = AgentTutor(store, model.model, FakeVerifier(APPROVE).model)
    result, _ = asyncio.run(approved.teach_with_trace(teach_request(FIRST, problem=BOOKS)))
    assert result.method is not None and result.reply_check.outcome == "approved"


def test_a_correct_subanswer_names_no_new_gap():
    """The rules clear a gap the model guessed from a right answer to part of the problem, so the agent carries the
    gap being taught instead (no representation-gap pollution from "24")."""
    d = apply_rules(ReasoningDraft.model_validate(BOOKS_LEFT), "24", recheck=False, has_tutor_message=True)
    assert d.main_gap is None and d.response_to == "tutor_question"


PROBE_RULE = "When main_gap is null the reply is a probe"  # the start of the conditional probe line in reply_prompt.txt


def test_the_verifier_gets_a_rule_only_where_it_applies():
    """The leak exception and the probe rule are sent only when they apply; any other check gets exactly the
    original prompt (an always-on extra rule shifted the verifier's other judgements)."""
    from pathlib import Path

    from app.verification.agent import reply_instructions
    from app.verification.schema import ReplyCheckInput

    # The prompt before the conditional lines were added (git show fce0b30:backend/app/verification/reply_prompt.txt),
    # kept as a file: reading it from git HEAD only worked while the prompt change was uncommitted, and git is not
    # installed in the Docker image. If the base prompt is changed on purpose, update this file in the same commit.
    original = (Path(__file__).parent / "data" / "reply_prompt_original.txt").read_text(encoding="utf-8")
    teach = ReplyCheckInput(problem="p", attempt="a", reply="r", main_gap="procedure")
    assert reply_instructions(teach) == original
    assert "[if" not in reply_instructions(teach)
    # (the base prompt already says "...the reply is a probe question" in its field list, so the probe rule is
    # recognised by its own sentence, not by the phrase "is a probe")
    assert "student_demonstrated" not in reply_instructions(teach)
    assert PROBE_RULE not in reply_instructions(teach)
    shown = teach.model_copy(update={"student_demonstrated": ["24 ÷ 6 = 4"]})
    assert "is not a leak: the student derived it" in reply_instructions(shown)
    assert PROBE_RULE in reply_instructions(teach.model_copy(update={"main_gap": None}))
