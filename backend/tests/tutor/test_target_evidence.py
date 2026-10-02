"""A gap is not carried onto work that demonstrates the current target.

From the live warehouse session (boxes_case.json: the problem, the student's two answers and the diagnosis model's own
proposals, as traced). Turn 1 left a recognition gap. In turn 2 the student derived the whole 2:3 allocation
(2 + 3 = 5, 324 ÷ 5 = 64.8, 64.8 × 2 = 129.6, 64.8 × 3 = 194.4) and every step was read correct, yet code carried the
turn-1 gap onto it, taught "recognising the method" again, and every draft failed the verifier. Now the evidence
resolves the target and the tutor asks about the next step; a false calculation or no new evidence still carries it.
"""

import asyncio
import json
from pathlib import Path

from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest
from app.tutor.agent import TARGET_SHOWN_REASON, AgentTutor
from app.user.service import SessionService

from .fakes import APPROVE, FOLLOW_UP_OK, FakeVerifier, ScriptedModel
from .test_transfer_regressions import COOKIES

CASE = json.loads((Path(__file__).parent / "boxes_case.json").read_text(encoding="utf-8"))
PROBLEM, (TURN1, TURN2), (PROPOSAL1, PROPOSAL2) = CASE["problem"], CASE["turns"], CASE["proposals"]
SETUP = {"concept_name": "Percentages and ratios", "steps": [
    "360 × 0.10 = 36 damaged", "360 - 36 = 324 remain", "2 + 3 = 5 parts", "324 ÷ 5 = 64.8 per part",
    "64.8 × 2 = 129.6 for Storage A", "64.8 × 3 = 194.4 for Storage B", "129.6 × 1.25 = 162 for Storage A",
    "5% of 360 = 18 transferred", "162 + 18 = 180 for Storage A", "194.4 - 18 = 176.4 for Storage B"],
    "result": "Storage A: 180 boxes, Storage B: 176.4 boxes"}
LAYOUT = "Draw two columns for Storage A and Storage B and split the 324 boxes in a 2:3 ratio."


def session(store, second_proposal):
    model = ScriptedModel([PROPOSAL1, second_proposal], replies=[LAYOUT, "What happens to Storage A next?"],
                          setup=SETUP, follow_ups=[COOKIES])
    verifier = FakeVerifier(APPROVE, follow_up_checks=[FOLLOW_UP_OK])
    svc = SessionService(AgentTutor(store, model.model, verifier.model), store, tracing=True)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id
    first = asyncio.run(svc.attempt(sid, TURN1))
    assert first.phase == "teach" and first.diagnosis.main_gap == "recognition"  # turn 1 as live
    return svc, sid, model


def diagnosed(store, sid):
    return [e.payload for e in store.list_trace_events(sid) if e.event_type == "DIAGNOSIS_RESULT"][-1]


def test_the_demonstrated_ratio_allocation_resolves_the_target_and_moves_to_the_next_step(store):
    svc, sid, model = session(store, PROPOSAL2)
    turn = asyncio.run(svc.attempt(sid, TURN2))
    d = diagnosed(store, sid)
    assert d.resolution_state == "CURRENT_TARGET_RESOLVED"
    assert d.gap_repaired and d.repair_reason == TARGET_SHOWN_REASON and not d.gap_carried
    assert d.main_gap is None and turn.diagnosis.main_gap is None  # no invented or stale gap reaches the student
    assert d.mode == "probe" and turn.method is None  # asks about the next step; no method to drift from
    assert d.current_target == "129.6 × 1.25 = 162 for Storage A"  # the next target: Storage A's 25% more
    assert {64.8, 129.6, 194.4} <= set(d.demonstrated_values)  # 5 is also a given, so it is never "demonstrated"
    assert turn.phase == "teach"  # the problem itself is not resolved yet


def test_a_false_calculation_in_the_allocation_still_carries_the_gap(store):
    wrong = json.loads(json.dumps(PROPOSAL2).replace("324 ÷ 5 = 64.8", "324 ÷ 5 = 65"))
    svc, sid, _ = session(store, wrong)
    turn = asyncio.run(svc.attempt(sid, TURN2.replace("324 ÷ 5 = 64.8", "324 ÷ 5 = 65")))
    d = diagnosed(store, sid)
    assert not d.gap_repaired and d.gap_carried and turn.diagnosis.main_gap == "recognition"


def test_no_new_evidence_still_carries_the_gap(store):
    nothing_new = {**PROPOSAL2, "steps": [{"role": "set_up", "status": "missing", "quote": None}], "main_gap": None,
                   "evidence": "insufficient", "confidence": "low", "error": None, "response_to": "clarification"}
    svc, sid, _ = session(store, nothing_new)
    turn = asyncio.run(svc.attempt(sid, "I don't know what to do next."))
    d = diagnosed(store, sid)
    assert d.resolution_state == "PREVIOUS_STEPS_CORRECT" and not d.gap_repaired
    assert turn.diagnosis.main_gap == "recognition"  # nothing demonstrated the target, so the gap stays
