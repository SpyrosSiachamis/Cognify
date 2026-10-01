"""The reply verifier on hand-written drafts: semantic method adherence and targeting.

    docker compose exec backend python -m pytest -m live tests/tutor/test_verifier_live.py -v -s
"""

import asyncio
import os

import pytest

from app.ai_gateway import gateway
from app.tutor.methods import METHOD_DEFINITIONS
from app.verification.agent import check_reply
from app.verification.schema import ReplyCheckInput

from .conftest import MARIA_FIRST_THOUGHT, PROBLEM, SOLUTION

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("TUTOR_MODEL_ID"), reason="set TUTOR_MODEL_ID to a Bedrock model ID"),
]

GAP_STEP = 'choose_method (missing): "I don\'t know how to get the height from the time"'


def check(reply: str, method: str):
    checked = asyncio.run(check_reply(ReplyCheckInput(
        problem=PROBLEM, attempt=MARIA_FIRST_THOUGHT, reply=reply, method=method, hints_used=0,
        hidden_solution=" ".join(SOLUTION.steps), main_gap="recognition", gap_step=GAP_STEP,
        method_definition=METHOD_DEFINITIONS[method], language="English",
    ), gateway.model_for()))
    print(checked)
    assert checked.ok
    return checked.value


def test_a_plain_question_is_not_visual_decomposition():
    result = check("You found the time to the top. What other quantities might help you find the height?",
                   "visual_decomposition")
    assert not result.approved and result.reason == "method_drift"


def test_decomposition_without_the_word_sketch_is_accepted():
    result = check(
        "You have the time to the top. Make two columns: what you know at launch and what you know at the "
        "highest point, and put the height you want in a third column marked '?'. Which column entries "
        "could link straight to that '?' without the time?",
        "visual_decomposition",
    )
    assert result.approved, result.note


def test_a_generic_move_is_off_target():
    result = check("Great effort! Remember that physics problems get easier with practice. What topic is this?",
                   "socratic")
    assert not result.approved and result.reason in ("off_target", "method_drift")


def test_a_targeted_socratic_question_is_accepted():
    result = check(
        "You already have the time to the top. During that time, how fast is the ball moving on average, "
        "and how could that help you find how far it went?",
        "socratic",
    )
    assert result.approved, result.note
