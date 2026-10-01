"""M4 offline: set_up, the personal stress test (F14/F15), the judge (F16) and learning from it (F17)."""

import asyncio

import pytest

from app.history.schema import Outcome
from app.seed.data import KINEMATICS_ID, MARIA_ID
from app.session.schema import SessionStartRequest, VerdictTurn
from app.tutor.agent import AgentTutor
from app.tutor.follow_up import FollowUpUnavailable, overlap
from app.tutor.schema import FollowUpDraft, Step
from app.tutor.setup import known_concepts
from app.tutor.strategy import choose_strategy
from app.user.ports import FollowUpRequest, JudgeRequest
from app.user.service import SessionService

from .conftest import PROBLEM, SOLUTION
from .fakes import FOLLOW_UP, FOLLOW_UP_OK, STUDENT_OK, FakeVerifier, ScriptedModel, diagnosis

STALL = diagnosis(("compute", "correct", "2.04 s"), ("choose_method", "missing", None), gap="recognition")
FOUND = diagnosis(("compute", "correct", "2.04 s"), ("choose_method", "correct", "v^2 = u^2 - 2gh"))
REJECT_FOLLOW_UP = {"mode": "follow_up_check", "approved": False, "reason": "invalid_followup",
                    "note": "It does not exercise choose_method."}


def tutor(store, model=None, verifier=None):
    model = model or ScriptedModel([STALL])
    verifier = verifier or FakeVerifier()
    return AgentTutor(store, model.model, verifier.model), model, verifier


def follow_up_request(**update) -> FollowUpRequest:
    fields = dict(
        student_id=MARIA_ID, problem=PROBLEM, concept_name="Constant-acceleration kinematics", solution=SOLUTION,
        main_gap="recognition", hints_used=1,
        student_answers=["I found the time, about 2.04 s, but not the height.", "So I use v^2 = u^2 - 2gh?"],
        last_steps=[Step(role="compute", status="correct", quote="2.04 s"), Step(role="choose_method", status="missing")],
        method="visual_decomposition",
    )
    return FollowUpRequest(**(fields | update))


# ---- set_up ----


def test_set_up_reuses_a_known_concept_name(store):
    t, model, _ = tutor(store)
    setup = asyncio.run(t.set_up("Solve 3x + 5 = 20.", "math"))
    assert model.setup_inputs[0]["known_concepts"] == ["Constant-acceleration kinematics"]
    assert setup.concept_name == "Constant-acceleration kinematics" and setup.solution.result == "20.4 m"
    assert known_concepts(store) == ["Constant-acceleration kinematics"]


def test_set_up_failure_raises_instead_of_inventing_a_solution(store):
    t, _, _ = tutor(store, ScriptedModel([STALL], setup={"nonsense": True}))
    with pytest.raises(RuntimeError, match="set_up failed"):
        asyncio.run(t.set_up("Solve 3x + 5 = 20.", None))


# ---- F14 + F15: the personal stress test ----


def test_follow_up_is_built_from_the_students_own_work(store):
    t, model, verifier = tutor(store)
    result = asyncio.run(t.follow_up(follow_up_request()))
    sent = model.follow_up_inputs[0]
    assert sent["student_answers"][0].startswith("I found the time")
    assert sent["gap_step"]["role"] == "choose_method" and sent["method"] == "visual_decomposition"
    assert result.output.follow_up.target_gap == "recognition"
    assert verifier.follow_up_inputs[0]["original_problem"] == PROBLEM
    assert result.reply_check.approved and "removing the support" in result.message


def test_a_paraphrase_of_the_original_is_rejected_by_code(store):
    paraphrase = {**FOLLOW_UP, "problem": "A ball is thrown upward at 25 m/s. How high does it go? (Use g = 9.8 m/s^2)"}
    model = ScriptedModel([STALL], follow_ups=[paraphrase, FOLLOW_UP])
    t, _, verifier = tutor(store, model)
    result = asyncio.run(t.follow_up(follow_up_request()))
    assert len(model.follow_up_inputs) == 2 and "original problem" in model.follow_up_inputs[1]["retry_note"]
    assert len(verifier.follow_up_inputs) == 1  # the paraphrase never reached the verifier
    assert result.output.follow_up.problem == FOLLOW_UP["problem"]


def test_a_rejected_follow_up_is_regenerated_with_the_reason(store):
    model = ScriptedModel([STALL])
    t, _, verifier = tutor(store, model, FakeVerifier(follow_up_checks=[REJECT_FOLLOW_UP, FOLLOW_UP_OK]))
    asyncio.run(t.follow_up(follow_up_request()))
    assert model.follow_up_inputs[1]["retry_reason"] == "invalid_followup"


def test_no_acceptable_follow_up_raises(store):
    t, _, _ = tutor(store, verifier=FakeVerifier(follow_up_checks=[REJECT_FOLLOW_UP]))
    with pytest.raises(FollowUpUnavailable):
        asyncio.run(t.follow_up(follow_up_request()))


def test_target_gap_is_the_taught_gap_or_transfer(store):
    model = ScriptedModel([STALL], follow_ups=[{**FOLLOW_UP, "target_gap": "procedure"}])
    t, _, _ = tutor(store, model)
    assert asyncio.run(t.follow_up(follow_up_request())).output.follow_up.target_gap == "recognition"
    assert asyncio.run(t.follow_up(follow_up_request(main_gap=None))).output.follow_up.target_gap == "transfer"


def test_overlap_measures_words_not_numbers():
    assert overlap("A ball is thrown up at 20 m/s.", "A ball is thrown up at 35 m/s.") == 1.0
    assert overlap(PROBLEM, FOLLOW_UP["problem"]) < 0.6


# ---- F16: the judge gives evidence; code decides ----

DRAFT = FollowUpDraft(**FOLLOW_UP)


def judge_request(text: str) -> JudgeRequest:
    return JudgeRequest(problem=PROBLEM, solution=SOLUTION, follow_up=DRAFT, student_text=text, hints_used=1)


def test_judge_passes_the_rubric_and_the_answer(store):
    t, _, verifier = tutor(store)
    result = asyncio.run(t.judge(judge_request("v^2 = u^2 - 2gh with v = 0 and u = 15, so h = 225 / 19.6 = 11.5 m")))
    assert result.correct and result.own_work
    assert verifier.student_inputs[0]["hidden_rubric"] == FOLLOW_UP["hidden_rubric"]


def test_a_bare_correct_number_is_not_independent_work(store):
    t, _, _ = tutor(store)  # the scripted judge says correct and own work
    result = asyncio.run(t.judge(judge_request("11.5 m")))
    assert result.correct and not result.own_work


def test_judge_failure_raises_never_passes(store):
    t, _, _ = tutor(store, verifier=FakeVerifier(student_checks=[{"mode": "student_check", "correct": "?"}]))
    with pytest.raises(RuntimeError, match="judge failed"):
        asyncio.run(t.judge(judge_request("h = 11.5 m because v^2 = u^2 - 2gh")))


# ---- the whole session on the real tutor, and F17 ----


def run_session(store, texts, student_checks=(STUDENT_OK,)):
    model = ScriptedModel([STALL, FOUND])
    verifier = FakeVerifier(student_checks=list(student_checks))
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id
    turns = [asyncio.run(svc.attempt(sid, text)) for text in texts]
    return sid, turns, model


ANSWERS = ["I found the time, about 2.04 s, but not the height.", "With 2.04 s known I could use v^2 = u^2 - 2gh.",
           "v^2 = u^2 - 2gh with v = 0 and u = 15, so h = 225 / 19.6, about 11.5 m."]


def test_full_session_on_the_real_tutor_reaches_a_verdict(store):
    sid, turns, model = run_session(store, ANSWERS)
    assert [t.phase for t in turns] == ["teach", "stress_test", "verdict"]
    assert turns[1].follow_up.problem == FOLLOW_UP["problem"]
    assert model.follow_up_inputs[0]["student_answers"] == ANSWERS[:2]
    verdict = turns[2]
    assert isinstance(verdict, VerdictTurn) and verdict.verdict.result == "VERIFIED"


def test_a_correct_but_bare_stress_test_answer_is_not_verified(store):
    sid, turns, _ = run_session(store, ANSWERS[:2] + ["11.5 m"])
    assert turns[2].verdict.result == "NOT YET" and not turns[2].verdict.independent


def test_outcome_is_recorded_and_changes_the_next_choice(store):
    before = choose_strategy(store, MARIA_ID, "recognition")
    assert (before.method, before.evidence.uses) == ("visual_decomposition", 9)
    run_session(store, ANSWERS)
    after = choose_strategy(store, MARIA_ID, "recognition")
    assert (after.evidence.uses, after.evidence.independent_successes) == (10, 8)  # learned from the outcome
    # Further failures for visual_decomposition change which method is best known.
    for _ in range(4):
        store.record_verdict(Outcome(
            student_id=MARIA_ID, session_id=None, concept_id=KINEMATICS_ID, gap_type="recognition",
            method="visual_decomposition", decision_mode="best_known", result="NOT YET", independent=False,
            hints_used=3, concept_before=store.get_concept_state(MARIA_ID, KINEMATICS_ID).state,
            concept_after="fragile", evidence="Seeded demo history: x",
            is_seeded=True,
        ))
    assert choose_strategy(store, MARIA_ID, "recognition").method != "visual_decomposition"


def test_judge_is_told_which_step_was_the_gap(store):
    t, _, verifier = tutor(store)
    asyncio.run(t.judge(judge_request("v^2 = u^2 - 2gh with v = 0, u = 15: h = 225 / 19.6 = 11.5 m")))
    sent = verifier.student_inputs[0]
    assert (sent["target_gap"], sent["target_step"]) == ("recognition", "choose_method")
