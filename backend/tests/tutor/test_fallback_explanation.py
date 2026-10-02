"""The explained safe fallback: when no teaching draft passed, the student is told why another answer is needed.

Built by code from the turn's diagnosis. It never claims uncertainty the student did not express, never shows an
internal label, quotes only the student, and does not ask again for working the student already sent.
"""

import asyncio
from typing import get_args

import pytest

from app.common.vocab import GapType, StepRole
from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest
from app.tutor.agent import AgentTutor
from app.tutor.fallback import explain_fallback
from app.tutor.schema import Step, TutorDiagnosis
from app.user.service import SessionService

from .fakes import FOLLOW_UP_OK, FakeVerifier, ScriptedModel, diagnosis
from .test_transfer_regressions import BOOKS, BOOKS_SETUP, COOKIES, FIRST, REJECT, WRONG_DIVISION

CINEMA_SETUP = "2 tickets × €30 = €60"
CINEMA_RESULT = "So I pay €40"


def read(*steps, gap="procedure", evidence="sufficient", confidence="medium", response_to="original_problem",
         error=None) -> TutorDiagnosis:
    data = diagnosis(*steps, gap=gap, evidence=evidence, confidence=confidence) | {"response_to": response_to}
    if error:
        data["error"] = error
    return TutorDiagnosis.model_validate(data)


def explain(d, text, gap_step=None, language="English", previous=None):
    return explain_fallback(d, gap_step, text, language, previous)


LABELS = [g for g in get_args(GapType)] + [r for r in get_args(StepRole)] + ["unobserved", "insufficient"]


def no_labels(reply: str) -> bool:
    lowered = reply.lower()
    return not any(label.replace("_", " ") in lowered or label in lowered for label in LABELS)


# ---- the kinds of explanation ----


def test_a_confident_student_with_a_missing_middle_step_is_asked_for_that_step_not_for_doubts():
    """The cinema case: sure of the €40, which is right, but the voucher step from €60 to €40 is not shown."""
    d = read(("set_up", "correct", CINEMA_SETUP), ("substitute", "missing", None), ("interpret", "correct", CINEMA_RESULT))
    text = f"I'm confident about this. {CINEMA_SETUP}. {CINEMA_RESULT}."
    reply, kind = explain(d, text, gap_step=Step(role="substitute", status="missing"))
    assert kind == "missing_step"
    assert reply == (f'Not yet: I can see "{CINEMA_RESULT}", but I need to see how you got there from '
                     f'"{CINEMA_SETUP}". Show me the step that leads to it.')
    assert "sure" not in reply.lower() and no_labels(reply)


def test_a_bare_answer_is_asked_for_its_calculation():
    d = read(("compute", "missing", None), gap=None, evidence="insufficient", confidence="low")
    reply, kind = explain(d, "€40")
    assert kind == "missing_reasoning"
    assert reply == "Not yet: I have your answer, but I need to see the calculation you used to get it."


def test_work_that_stops_early_is_asked_for_the_next_step():
    d = read(("compute", "correct", CINEMA_SETUP), ("interpret", "missing", None))
    reply, kind = explain(d, CINEMA_SETUP, gap_step=Step(role="interpret", status="missing"))
    assert kind == "missing_step"
    assert reply == (f'Not yet: I can follow your work up to "{CINEMA_SETUP}", but the next step is not there yet. '
                     "Show me what you do next.")


def test_uncertainty_is_mentioned_only_when_the_student_said_it():
    d = read(("set_up", "correct", CINEMA_SETUP), ("substitute", "missing", None), ("interpret", "correct", CINEMA_RESULT))
    unsure = f"I'm not sure about the voucher step. {CINEMA_SETUP}. {CINEMA_RESULT}."
    reply, kind = explain(d, unsure)
    assert kind == "student_uncertain"
    assert reply.startswith('You said: "I\'m not sure about the voucher step"')
    for confident in (f"I'm sure. {CINEMA_SETUP}. {CINEMA_RESULT}.", f"I think {CINEMA_SETUP}. {CINEMA_RESULT}."):
        reply, kind = explain(d, confident)
        assert kind != "student_uncertain" and "sure" not in reply.lower()


def test_an_incorrect_step_is_named_with_the_students_words_and_never_the_correction():
    error = {"student_did": "took 20 from 60 and got 30", "actually_gives": "60 - 20 is 40",
             "asked_for": "60 - 20 = 40", "mismatch": "60 - 20 is 40, not 30"}
    d = read(("set_up", "correct", CINEMA_SETUP), ("compute", "wrong", "60 - 20 = 30"), error=error)
    reply, kind = explain(d, f"{CINEMA_SETUP}, then 60 - 20 = 30.", gap_step=Step(role="compute", status="wrong",
                                                                                  quote="60 - 20 = 30"))
    assert kind == "incorrect_step"
    assert reply == ('Not yet: one step does not hold up yet: "60 - 20 = 30". Look at that step again and show me how '
                     "you work it out.")
    assert "40" not in reply and no_labels(reply)  # nothing from the error analysis or the solution


def test_working_the_diagnosis_could_not_place_is_not_asked_for_again():
    """Evidence provided but read as another problem's work: say the matching failed, do not ask for it as missing."""
    d = read(("choose_method", "missing", None), gap=None, evidence="insufficient", confidence="low",
             response_to="other_problem")
    text = "For the jacket I subtract the discount from the price: €75 - €15 = €60. The sale price is €60."
    reply, kind = explain(d, text)
    assert kind == "unrecognized_evidence"
    assert "show me the calculation" not in reply.lower() and "not sure" not in reply.lower()


def test_the_same_request_is_not_repeated_after_the_student_answered_it_with_working():
    d = read(("set_up", "correct", CINEMA_SETUP), ("substitute", "missing", None), ("interpret", "correct", CINEMA_RESULT))
    text = f"{CINEMA_SETUP}. I use the voucher and {CINEMA_RESULT}."
    first, _ = explain(d, text, gap_step=Step(role="substitute", status="missing"))
    again, kind = explain(d, text, gap_step=Step(role="substitute", status="missing"), previous=first)
    assert kind == "unrecognized_evidence" and again != first
    # A bare answer repeated is still a bare answer: asking for the calculation again is right.
    bare = read(("compute", "missing", None), gap=None, evidence="insufficient", confidence="low")
    asked, _ = explain(bare, "€40")
    assert explain(bare, "€40", previous=asked) == (asked, "missing_reasoning")


def test_an_answer_to_the_tutors_sub_question_is_read_as_work_and_asked_for_the_next_step():
    """From the jacket session: "$120 + $8 = $128" answering the tutor's question is recognised work, so the
    fallback moves on to the next operation instead of saying the working could not be matched."""
    d = read(("compute", "correct", "$120 + $8 = $128"), ("set_up", "missing", None), response_to="tutor_question")
    reply, kind = explain(d, "$120. The $8 shipping fee is added to the discounted price, so $120 + $8 = $128.",
                          gap_step=Step(role="set_up", status="missing"))
    assert kind == "missing_step" and '"$120 + $8 = $128"' in reply and "could not match" not in reply


def test_nothing_to_go_on_gets_a_neutral_request_that_claims_nothing():
    d = read(("choose_method", "missing", None), gap=None, evidence="insufficient", confidence="low",
             response_to="acknowledgement")
    reply, kind = explain(d, "ok")
    assert kind == "general" and "sure" not in reply.lower() and no_labels(reply)


def test_greek_students_get_the_explanation_in_greek():
    d = read(("compute", "missing", None), gap=None, evidence="insufficient", confidence="low")
    reply, _ = explain(d, "40", language="Greek")
    assert reply.startswith("Όχι ακόμα")


def test_long_quotes_are_shortened():
    long = "2 tickets × €30 = €60 " + "and then some more words " * 10
    d = read(("compute", "correct", long), ("interpret", "missing", None))
    reply, _ = explain(d, long)
    assert "…" in reply and len(reply) < 220


# ---- in the real turn ----


def test_the_student_sees_the_explanation_and_it_is_not_a_hint(store):
    model = ScriptedModel([WRONG_DIVISION, WRONG_DIVISION], replies=["(rejected 1)", "(rejected 2)"],
                          setup=BOOKS_SETUP, follow_ups=[COOKIES])
    verifier = FakeVerifier(REJECT, follow_up_checks=[FOLLOW_UP_OK])
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store, tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=BOOKS, student_id=MARIA_ID))).session_id
    turn = asyncio.run(svc.attempt(sid, FIRST))
    assert turn.reply_check.outcome == "verifier_rejected"
    assert turn.message.startswith('Not yet: one step does not hold up yet: "24 ÷ 6 = 5"')
    fallback, = [e.payload for e in store.list_trace_events(sid) if e.event_type == "TEACHING_FALLBACK"]
    assert (fallback.explanation, fallback.evidence_unrecognized, fallback.fallback_reply) == (
        "incorrect_step", False, turn.message)
    nxt = asyncio.run(svc.attempt(sid, "Hmm, 24 ÷ 6 = 4."))
    assert nxt.hints_used == 0  # still not a hint
    assert model.reasoning_inputs[-1]["tutor_message"] == turn.message  # the next answer is read against it
