"""A wrong label is cleared only by evidence that the labelled claim holds.

Replays the live rectangle session (rectangle_stale_case.json: every answer, the tutor message each answered and the
diagnosis model's own proposals, as traced). The student wrote "w² + 2w - 48 = 0" in an answer with no wrong step,
then "I would factor it as (w + 8)(w - 6) = 0." The model labelled that factorization wrong (and, for the same
quote, correct), and the label was stored. The next answer solved the factors: "w+8 = 0 and w-6 = 0. So w=-8 or
w = 6. However width cannot be negative so w = 6". Live, the model re-asserted the stale label (from the tutor's own
quote of it) and the session stayed stuck on it.

The factorization is the same equation as the student's earlier correct "w² + 2w - 48 = 0", and every value the
later answer states solves both: that evidence establishes the challenged claim, so code clears the label. The rule
is equivalence of equations (algebra.equivalent), never the phrase, and never "later wins": a factorization that is
really wrong, or a stated value that solves neither, keeps the label.
"""

import asyncio
import json
from pathlib import Path

from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest
from app.tutor.agent import AgentTutor
from app.tutor.algebra import equations, equivalent
from app.tutor.resolution import ESTABLISHED_REASON, established_equations, resolve_challenge
from app.tutor.schema import PriorDiagnosis, Step, TutorDiagnosis
from app.user.service import SessionService

from .fakes import FOLLOW_UP_OK, FakeVerifier, ScriptedModel
from .test_transfer_regressions import COOKIES, REJECT

CASE = json.loads((Path(__file__).parent / "rectangle_stale_case.json").read_text(encoding="utf-8"))
PROBLEM, TURNS, PROPOSALS = CASE["problem"], CASE["turns"], CASE["proposals"]
SETUP = {"concept_name": CASE["concept_name"], "steps": CASE["solution_steps"], "result": CASE["solution_result"]}
FACTORED, SOLVED = TURNS[-2:]
CLAIM = "(w + 8)(w - 6) = 0"
CLEAN = ["w * (w + 2) = 48", "w² + 2w - 48 = 0"]  # the student's earlier correct work, from answers with no wrong step
# Live, the factorization's labels were asked about once (the recheck) on both of the last two turns, and the traced
# proposal is the model's second answer: the replay gives each of those twice.
LIVE = PROPOSALS[:-2] + [PROPOSALS[-2]] * 2 + [PROPOSALS[-1]] * 2
LENGTH = "The length is w + 2 = 6 + 2 = 8 m, so the rectangle is 6 m wide and 8 m long."
LENGTH_READ = {
    "steps": [{"role": "compute", "status": "correct", "quote": "w + 2 = 6 + 2 = 8"},
              {"role": "interpret", "status": "correct", "quote": "the rectangle is 6 m wide and 8 m long"}],
    "dimensions": [], "main_gap": None, "alternatives": [], "confidence": "high", "evidence": "sufficient",
    "error": None, "response_to": "tutor_question",
}


def session(store, proposals):
    model = ScriptedModel(proposals, replies=["(rejected 1)", "(rejected 2)"], setup=SETUP, follow_ups=[COOKIES])
    verifier = FakeVerifier(REJECT, follow_up_checks=[FOLLOW_UP_OK])  # every draft rejected, as live at the end
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store, tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id
    return svc, sid


def send(svc, sid, text):
    return asyncio.run(svc.attempt(sid, text))


def events(store, sid, kind):
    return [e.payload for e in store.list_trace_events(sid) if e.event_type == kind]


def last_steps(store, sid):
    return [(s.role, s.status) for s in store.list_steps(store.list_attempts(sid)[-1].id)]


# ---- the live session ----


def test_the_stale_factorization_label_is_cleared_by_the_students_evidence(store):
    svc, sid = session(store, LIVE)
    for text in TURNS[:-1]:
        send(svc, sid, text)
    assert ("compute", "wrong") in last_steps(store, sid)  # the stored label, as live
    send(svc, sid, SOLVED)
    assert not any(status == "wrong" for _, status in last_steps(store, sid))
    diagnosed = events(store, sid, "DIAGNOSIS_RESULT")[-1]
    assert diagnosed.resolved_by_correct_work and diagnosed.gap_repaired
    assert diagnosed.repair_reason == ESTABLISHED_REASON
    assert diagnosed.main_gap is None and diagnosed.mode != "teach"  # no replacement gap is taught
    assert diagnosed.resolution_state != "PROBLEM_RESOLVED"  # the length is not given yet: support stays


def test_the_length_then_resolves_the_problem(store):
    svc, sid = session(store, LIVE + [LENGTH_READ])
    for text in TURNS:
        send(svc, sid, text)
    reply = send(svc, sid, LENGTH)
    diagnosed = events(store, sid, "DIAGNOSIS_RESULT")[-1]
    assert diagnosed.resolution_state == "PROBLEM_RESOLVED", diagnosed
    assert reply.phase == "stress_test"


# ---- the rule, and what it never clears ----


def prior() -> PriorDiagnosis:
    return PriorDiagnosis(steps=[Step(role="compute", status="wrong", quote=CLAIM)], main_gap="procedure")


def reread(quote: str = CLAIM) -> TutorDiagnosis:
    """The live re-reading of the solved answer: the claim re-asserted wrong next to correct work."""
    return TutorDiagnosis.model_validate({
        **PROPOSALS[-1], "steps": [{"role": "set_up", "status": "wrong", "quote": quote},
                                   *PROPOSALS[-1]["steps"][1:3]],
    })


def resolve(attempt: str = SOLVED, clean: list[str] = CLEAN, diagnosis: TutorDiagnosis | None = None):
    return resolve_challenge(prior(), diagnosis or reread(), attempt, {48.0, 2.0}, [], clean)


def test_equivalent_reads_the_same_equation_in_any_form():
    (factored,), (expanded,), (area,) = equations(CLAIM), equations("w² + 2w - 48 = 0"), equations("w(w + 2) = 48")
    assert equivalent(factored, expanded) and equivalent(factored, area) and equivalent(area, expanded)
    (swapped,), (scaled,) = equations("(w + 6)(w - 8) = 0"), equations("2w² + 4w = 96")
    assert not equivalent(factored, swapped) and equivalent(scaled, expanded)
    (identity,) = equations("(w + 8)(w - 6) = w² + 2w - 48")
    assert not equivalent(identity, expanded)  # an identity is no equation


def test_the_solved_answer_resolves_the_challenge():
    resolved = resolve()
    assert resolved is not None and resolved.established_equation
    assert not any(s.status == "wrong" for s in resolved.diagnosis.steps) and resolved.diagnosis.main_gap is None


def test_a_factorization_that_is_really_wrong_keeps_its_label():
    wrong = "(w + 6)(w - 8) = 0"
    assert established_equations(wrong, "w+6 = 0 and w-8 = 0. So w = -6 or w = 8.", CLEAN) == []
    assert resolve_challenge(PriorDiagnosis(steps=[Step(role="compute", status="wrong", quote=wrong)],
                                            main_gap="procedure"),
                             reread(wrong), "w+6 = 0 and w-8 = 0. So w = -6 or w = 8.", {48.0, 2.0}, [], CLEAN) is None


def test_without_earlier_correct_work_to_rest_on_the_label_stands():
    assert resolve(clean=[]) is None  # the hidden solution is never the evidence


def test_a_stated_value_that_solves_neither_keeps_the_label():
    assert resolve(attempt="w+8 = 0 and w-6 = 0. So w = -8 or w = 5.") is None


def test_an_answer_that_states_no_value_does_not_establish_the_claim():
    assert resolve(attempt="I checked it again and I think it is right.") is None


def test_another_wrong_claim_in_the_answer_still_stands():
    other = TutorDiagnosis.model_validate({
        **PROPOSALS[-1], "steps": [{"role": "set_up", "status": "wrong", "quote": CLAIM},
                                   {"role": "interpret", "status": "wrong",
                                    "quote": "However width cannot be negative so w = 6"}],
    })
    assert resolve(diagnosis=other) is None  # only a restatement of the established equation is cleared
