"""The 14 tutor test cases against the real model (case numbers from the test plan).

    docker compose exec backend python -m pytest -m live tests/tutor/test_cases_live.py -v -s

Each case prints the turn's trace, so a failure can be read, not just counted.
"""

import asyncio
import os
import re

import pytest

from app.seed.data import MARIA_ID
from app.session.schema import SessionStartRequest
from app.tutor import agent as agent_module
from app.tutor.agent import AgentTutor
from app.tutor.language import ACKNOWLEDGE_REPLY, student_language, written_in
from app.tutor.schema import ChooseStrategyResult, EvidenceCounts, PriorDiagnosis, Step
from app.user.service import SessionService
from app.verification.agent import check_reply
from app.verification.schema import ReplyCheckInput

from .conftest import MARIA_FIRST_THOUGHT, PROBLEM, SOLUTION, teach_request

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("TUTOR_MODEL_ID"), reason="set TUTOR_MODEL_ID to a Bedrock model ID"),
]

ANSWERS = ["20.4 m", "20.4m", "20.41"]
PRAISE_FOR_ANSWER = re.compile(r"(correct answer|that'?s right|you got it|well done|exactly right|is correct)", re.I)
STUCK = "I know the time is 2.04 seconds but I'm stuck."


@pytest.fixture
def tutor(store) -> AgentTutor:
    return AgentTutor(store)


def teach(tutor: AgentTutor, text: str, **update):
    result = asyncio.run(tutor.teach(teach_request(text, **update)))
    print(tutor.last_trace.model_dump_json(indent=2))
    print("TO STUDENT:", result.output.reply)
    assert written_in(result.output.reply, student_language(text)), "reply not in the student's language"
    return result


def statuses(result) -> list[str]:
    return [step.status for step in result.output.steps]


def rating(result, name: str) -> str | None:
    return next((d.state for d in result.output.dimensions if d.name == name), None)


# ---- case 1: wrong answer from a wrong idea (v / g is a time, not a height) ----


def test_case_01_wrong_reasoning_is_found_and_not_praised(tutor):
    result = teach(tutor, "The height is 20 / 9.8 = 2.04 m because I divided the velocity by gravity.")
    assert "wrong" in statuses(result)
    wrong_quotes = " ".join(s.quote or "" for s in result.output.steps if s.status == "wrong")
    assert re.search(r"20 / 9.8|2.04 m|divided", wrong_quotes)
    assert rating(result, "correctness") in (None, "weak", "fragile")
    assert not PRAISE_FOR_ANSWER.search(result.output.reply)
    assert re.search(r"time|unit|second", result.output.reply, re.I), "the move should target what v/g really gives"
    assert not any(a in result.output.reply for a in ANSWERS)


# ---- case 2: partially correct (Maria's first thought) ----


def test_case_02_partial_reasoning_credits_the_time_and_finds_the_stall(tutor):
    result = teach(tutor, MARIA_FIRST_THOUGHT)
    out = result.output
    assert any(s.status == "correct" and "2.04" in (s.quote or "") for s in out.steps)
    assert not any(s.status == "wrong" and "know" in (s.quote or "") for s in out.steps), "not knowing is missing"
    assert out.main_gap in ("recognition", "strategy_choice")
    assert result.reply_check.approved
    assert re.search(r"sketch|draw|diagram|picture|mark|label", out.reply, re.I), "visual_decomposition move"
    # The move connects what she has (the time) to what she wants (the height), not just "sketch it".
    assert re.search(r"\btime\b", out.reply, re.I) and re.search(r"height|high", out.reply, re.I), "move not tied to her gap"


# ---- case 3: completely correct ----

CORRECT_WORK = "At the highest point, v = 0. 0 = 20 - 9.8t, so t = 2.04 s. Then h = 20(2.04) - 4.9(2.04)^2 = 20.4 m."


def test_case_03_correct_work_gets_no_invented_gap(tutor):
    result = teach(tutor, CORRECT_WORK)
    assert set(statuses(result)) == {"correct"}
    assert result.output.main_gap is None
    assert "weak" not in [d.state for d in result.output.dimensions]
    assert result.method is None and result.output.reply == ACKNOWLEDGE_REPLY["English"]


def test_case_03_correct_work_moves_toward_the_stress_test(store):
    svc = SessionService(AgentTutor(store), store)
    sid = asyncio.run(svc.start(SessionStartRequest(problem=PROBLEM, student_id=MARIA_ID))).session_id
    turn = asyncio.run(svc.attempt(sid, CORRECT_WORK))
    print(turn.model_dump_json(indent=2))
    assert turn.phase == "stress_test"


# ---- case 4: right intermediate, wrong method for the height ----


def test_case_04_wrong_displacement_method_is_pinpointed(tutor):
    result = teach(tutor, "The ball takes 2.04 seconds to reach the top. Since it starts at 20 m/s, the height must be 20 x 2.04 = 40.8 m.")
    out = result.output
    assert any(s.status == "correct" and "2.04" in (s.quote or "") for s in out.steps)
    assert any(s.status == "wrong" and re.search(r"40.8|20 x 2.04", s.quote or "") for s in out.steps)
    assert out.main_gap is not None
    assert not any(a in out.reply for a in ANSWERS)


# ---- case 5: no useful reasoning ----


def test_case_05_no_reasoning_gets_a_probe_not_a_label(tutor):
    result = teach(tutor, "I don't know.")
    out = result.output
    assert (out.evidence, out.confidence, out.main_gap) == ("insufficient", "low", None)
    assert result.method is None and tutor.last_trace.mode == "probe"
    assert out.reply.strip().endswith("?") and len(out.reply) < 250


# ---- case 6: misconception ----


def test_case_06_velocity_zero_is_not_acceleration_zero(tutor):
    result = teach(tutor, "At the highest point the acceleration is zero because the ball has stopped, so I can use a = 0.")
    assert result.output.main_gap == "concept"
    assert any(s.status == "wrong" and "acceleration" in (s.quote or "") for s in result.output.steps)
    assert re.search(r"accelerat|gravity", result.output.reply, re.I)


# ---- case 7: history must not override current evidence ----


def test_case_07_correct_work_beats_a_recognition_history(tutor):
    result = teach(tutor, "I used v^2 = u^2 + 2as. At the top v = 0, so 0 = 20^2 + 2(-9.8)h, giving h = 20.4 m.")
    assert "wrong" not in statuses(result)
    assert result.output.main_gap != "recognition"
    assert rating(result, "recognition") in (None, "strong")


# ---- case 8: same answer, different strategies ----

STRATEGY_MOVES = {
    "visual_decomposition": r"sketch|draw|diagram|picture|mark|label",
    "socratic": r"\?",
    "worked_example": r"example|suppose|imagine|consider|say a|for instance|simpler|similar|another ball",
}


def test_case_08_strategy_changes_the_move_not_the_diagnosis(tutor, monkeypatch):
    gaps, reasoning_inputs = {}, []
    real_diagnose = agent_module.diagnose

    async def recording_diagnose(reasoning_input, model, timeout):
        reasoning_inputs.append(reasoning_input.model_dump())
        return await real_diagnose(reasoning_input, model, timeout)

    monkeypatch.setattr(agent_module, "diagnose", recording_diagnose)
    for method, pattern in STRATEGY_MOVES.items():
        pinned = ChooseStrategyResult(method=method, mode="best_known", reason=f"Test strategy: {method}.",
                                      evidence=EvidenceCounts(uses=9, independent_successes=7))
        monkeypatch.setattr(agent_module, "choose_strategy", lambda *args, pinned=pinned: pinned)
        print(f"\n===== {method}")
        result = teach(tutor, MARIA_FIRST_THOUGHT)
        assert result.reply_check.approved, f"{method}: fell back"
        gaps[method] = result.output.main_gap
        assert re.search(pattern, result.output.reply, re.I), f"{method} move not visible: {result.output.reply}"
    assert all(i == reasoning_inputs[0] for i in reasoning_inputs), "the reasoning step saw the strategy"
    assert len(set(gaps.values())) == 1, f"diagnosis changed between runs: {gaps}"


# ---- case 9: answer leakage ----


def test_case_09_stuck_student_gets_scaffolding_not_the_answer(tutor):
    result = teach(tutor, STUCK)
    assert result.reply_check.approved, "legitimate scaffolding should be approved"
    assert not any(a in result.output.reply for a in ANSWERS)


def _check(model, reply: str):
    checked = asyncio.run(check_reply(ReplyCheckInput(
        problem=PROBLEM, attempt=STUCK, reply=reply, method="visual_decomposition", hints_used=1,
        hidden_solution=" ".join(SOLUTION.steps),
    ), model))
    print(checked)
    assert checked.ok
    return checked.value


def test_case_09_verifier_rejects_a_leak_written_in_words(tutor):
    check = _check(tutor._verifier_model, "Good work on the time! The ball ends up a bit more than twenty metres high, about twenty point four.")
    assert not check.approved and check.reason == "answer_leak"


# ---- case 10: heavy hint ----


def test_case_10_verifier_rejects_a_heavy_hint(tutor):
    check = _check(tutor._verifier_model, "Use h = ut + 1/2 at^2, substitute u = 20, t = 2.04, and a = -9.8.")
    assert not check.approved and check.reason in ("heavy_hint", "answer_leak")


# ---- case 13 and 14: the loop after a teaching move ----

TEACHING = "What equation relates displacement, initial velocity, time, and acceleration?"
PRIOR = PriorDiagnosis(
    steps=[Step(role="compute", status="correct", quote="I found the time to the top"),
           Step(role="choose_method", status="missing")],
    main_gap="recognition",
)


def test_case_13_student_finds_the_equation_and_the_gap_is_repaired(tutor):
    result = teach(tutor, "h = ut + 1/2 at^2, so I can use u = 20, t = 2.04, a = -9.8.", first_thought=False,
                   hints_used=1, prior=PRIOR)
    assert result.output.gap_repaired
    assert "what equation relates" not in result.output.reply.lower()


def test_case_14_student_still_stuck_is_not_repaired(tutor):
    result = teach(tutor, "I still don't know.", first_thought=False, hints_used=1, prior=PRIOR)
    assert not result.output.gap_repaired
    assert result.method is not None and tutor.last_trace.mode == "teach"
    assert result.output.main_gap == "recognition"
    assert result.output.reply.strip() != TEACHING
