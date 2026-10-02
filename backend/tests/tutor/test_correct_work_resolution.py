"""A correction resolves the challenged step; it never starts a search for a new one.

Replays the live laptop session (laptop_case.json: the problem, the student's two answers and the diagnosis model's
own proposals, exactly as traced). Turn 1 marked the transfer step wrong; in turn 2 the student proved every value
in it, and the diagnosis moved the wrong label onto that proof and the conclusion. Now the proof resolves the gap
and the session reaches the fresh problem; a false calculation or a new value still keeps the diagnosis.
"""

import asyncio
import json
from pathlib import Path

import pytest

from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest
from app.tutor.agent import AgentTutor
from app.tutor.evidence import numeric_values
from app.tutor.resolution import contradictions, resolve_challenge, validated_values
from app.tutor.schema import PriorDiagnosis, Step, TutorDiagnosis
from app.user.service import SessionService

from .fakes import FOLLOW_UP_OK, FakeVerifier, ScriptedModel
from .test_transfer_regressions import COOKIES, REJECT

CASE = json.loads((Path(__file__).parent / "laptop_case.json").read_text(encoding="utf-8"))
PROBLEM, (TURN1, TURN2) = CASE["problem"], CASE["turns"]
PROPOSAL1, PROPOSAL2 = CASE["proposals"]
# The live set-up step's (rounded) solution: the resolution must not depend on the final answer matching.
SETUP = {"concept_name": "Percentages and ratios", "steps": ["Lab A: 127 laptops, Lab B: 118 laptops"],
         "result": "Lab A: 127 laptops, Lab B: 118 laptops"}
GIVEN = numeric_values(PROBLEM)
CHALLENGED = "I transfer 24 laptops from Lab B to Lab A, giving Lab A 126.6 and Lab B 118.5."


def with_text(proposal: dict, old: str, new: str) -> dict:
    """The same proposal for an answer where one phrase was written differently."""
    return json.loads(json.dumps(proposal).replace(old, new))


def session(store, proposals):
    model = ScriptedModel(proposals, replies=["(rejected 1)", "(rejected 2)"], setup=SETUP, follow_ups=[COOKIES])
    verifier = FakeVerifier(REJECT, follow_up_checks=[FOLLOW_UP_OK])  # every draft rejected, as live (method_drift)
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store, tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id
    return svc, sid, model


def send(svc, sid, text):
    return asyncio.run(svc.attempt(sid, text))


def events(store, sid, kind):
    return [e.payload for e in store.list_trace_events(sid) if e.event_type == kind]


# ---- the laptop session ----


def test_the_laptop_correction_resolves_the_gap_and_reaches_the_fresh_problem(store):
    """incorrect diagnosis -> student proves the step -> gap resolves -> no replacement gap -> fresh problem."""
    svc, sid, model = session(store, [PROPOSAL1, PROPOSAL2])
    first = send(svc, sid, TURN1)
    assert first.phase == "teach" and first.message.startswith(f'Not yet: one step does not hold up yet: "{CHALLENGED[:-1]}')
    second = send(svc, sid, TURN2)
    assert second.phase == "stress_test" and second.follow_up.problem == COOKIES["problem"]
    assert model.reasoning_calls == 2  # one per turn: no extra model call, no recheck
    turn2 = store.list_attempts(sid)[-1]
    assert not any(s.status == "wrong" for s in store.list_steps(turn2.id))  # no replacement gap was stored
    diagnosed = events(store, sid, "DIAGNOSIS_RESULT")[-1]
    assert diagnosed.resolved_by_correct_work and diagnosed.gap_repaired and diagnosed.mode == "acknowledge"
    assert {24.0, 102.6, 126.6, 142.5, 118.5} <= set(diagnosed.validated_values)
    assert not GIVEN & set(diagnosed.validated_values)  # givens are never validated on their own
    removed, = events(store, sid, "SUPPORT_REMOVED")
    # Support goes only because the problem is resolved by the student's work (the rounded 127/118 match 126.6/118.5).
    assert removed.reason == "problem_resolved" and diagnosed.resolution_state == "PROBLEM_RESOLVED"
    assert len(events(store, sid, "FRESH_PROBLEM_GENERATED")) == 1


def test_valid_evidence_next_to_a_genuine_contradiction_keeps_the_diagnosis(store):
    """The proof of the challenged values is there, but the conclusion contradicts it: not resolved."""
    text = TURN2.replace("Lab B has 118.5 laptops.", "Lab B has 130 laptops.")
    proposal = with_text(PROPOSAL2, "Lab B has 118.5 laptops.", "Lab B has 130 laptops.")
    svc, sid, _ = session(store, [PROPOSAL1, proposal])
    send(svc, sid, TURN1)
    turn = send(svc, sid, text)
    assert turn.phase == "teach"
    diagnosed = events(store, sid, "DIAGNOSIS_RESULT")[-1]
    assert not diagnosed.resolved_by_correct_work and not diagnosed.gap_repaired
    assert any(s.status == "wrong" for s in store.list_steps(store.list_attempts(sid)[-1].id))


@pytest.mark.parametrize("wrong_line, right_line", [
    ("102.6 + 24 = 130", "102.6 + 24 = 126.6"),
    ("142.5 − 24 = 130", "142.5 − 24 = 118.5"),
    ("10% of the original 240 is 30", "10% of the original 240 is 24"),
])
def test_genuinely_incorrect_arithmetic_is_never_accepted(store, wrong_line, right_line):
    svc, sid, _ = session(store, [PROPOSAL1, with_text(PROPOSAL2, right_line, wrong_line)])
    send(svc, sid, TURN1)
    turn = send(svc, sid, TURN2.replace(right_line, wrong_line))
    assert turn.phase == "teach"
    assert not events(store, sid, "DIAGNOSIS_RESULT")[-1].resolved_by_correct_work


# ---- the rule itself ----

TURN1_CORRECT = [s["quote"] for s in PROPOSAL1["steps"] if s["status"] == "correct"]
PRIOR = PriorDiagnosis(steps=[Step(role="set_up", status="wrong", quote=CHALLENGED)], main_gap="representation")


def diagnosis_of(proposal: dict) -> TutorDiagnosis:
    data = {k: v for k, v in proposal.items() if k in TutorDiagnosis.model_fields}
    return TutorDiagnosis.model_validate(data | {"response_to": proposal.get("response_to", "original_problem")})


def test_validated_values_need_provenance_and_givens_never_validate_alone():
    validated = validated_values(GIVEN, TURN1_CORRECT, TURN2)
    assert {102.6, 142.5, 24.0, 126.6, 118.5} <= validated and not GIVEN & validated
    # Without the earlier correct work, 102.6 and 142.5 have no provenance, so nothing built on them validates.
    bare = validated_values(GIVEN, [], TURN2)
    assert 24.0 in bare and 126.6 not in bare and 118.5 not in bare
    # Restating the givens proves nothing.
    assert validated_values(GIVEN, [], "The transfer is 10% of the original 240 laptops.") == set()


def test_a_false_calculation_or_an_underived_value_is_a_contradiction():
    validated = validated_values(GIVEN, TURN1_CORRECT, TURN2)
    assert contradictions("102.6 + 24 = 130", [], GIVEN, validated)
    assert contradictions("10% of 240 = 30", [], GIVEN, validated)
    assert contradictions(TURN2, [Step(role="interpret", status="wrong", quote="Lab B has 130 laptops.")], GIVEN, validated)
    assert not contradictions(TURN2, [Step(role="interpret", status="wrong", quote="Lab B has 118.5 laptops.")],
                              GIVEN, validated)


def test_only_a_proof_resolves_a_claim_or_a_restatement_does_not():
    d = diagnosis_of(PROPOSAL2)
    assert resolve_challenge(PRIOR, d, TURN2, GIVEN, TURN1_CORRECT) is not None
    claim = "I am sure that Lab A has 126.6 laptops and Lab B has 118.5 laptops."
    assert resolve_challenge(PRIOR, d, claim, GIVEN, TURN1_CORRECT) is None


def test_a_missing_step_is_left_to_the_existing_repair_path():
    prior = PriorDiagnosis(steps=[Step(role="set_up", status="missing")], main_gap="representation")
    assert resolve_challenge(prior, diagnosis_of(PROPOSAL2), TURN2, GIVEN, TURN1_CORRECT) is None
