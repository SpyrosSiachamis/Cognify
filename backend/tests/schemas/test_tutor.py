import copy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.tutor.schema import (
    ChooseStrategyInput,
    ChooseStrategyResult,
    Level1Answer,
    TutorFollowUpOutput,
    TutorTeachingOutput,
)

MARIA = "16e82ef2-adee-4671-8393-c6b50ac91672"

STRATEGY_INPUT = {"student_id": MARIA, "gap_type": "recognition", "concept": "constant-acceleration kinematics"}
STRATEGY_RESULT = {
    "method": "visual_decomposition", "mode": "best_known",
    "reason": "Worked 7 of 9 times for you on recognition gaps.",
    "evidence": {"uses": 9, "independent_successes": 7}, "last_success_days_ago": 6,
}
TEACHING = {
    "steps": [
        {"role": "identify_quantities", "status": "correct", "quote": "initial velocity of 20 m/s"},
        {"role": "choose_method", "status": "wrong", "quote": "I do not know how to get the height from the time"},
    ],
    "dimensions": [
        {"name": "recognition", "state": "weak", "evidence": "Found the time but did not see a way to get the height."},
        {"name": "procedure", "state": "strong", "evidence": "Time to the top computed correctly."},
    ],
    "main_gap": "recognition",
    "alternatives": [{"gap": "representation", "confidence": "low"}],
    "confidence": "medium",
    "gap_repaired": False,
    "reply": "Let's draw it. Sketch the ball going up and mark where its speed becomes 0.",
}
FOLLOW_UP = {
    "follow_up": {
        "problem": "A stone is launched upward at 15 m/s from a balcony. How far above the balcony does it rise?",
        "concept_invariant": "Constant-acceleration motion; choose the equation that needs no time.",
        "target_gap": "recognition", "target_step": "choose_method",
        "perturbation": "context", "difficulty": "medium",
        "hidden_rubric": ["Chooses v^2 = u^2 - 2gh", "Reports about 11.5 m"],
    }
}


def bad(base, **changes):
    data = copy.deepcopy(base)
    data.update(changes)
    return data


def test_contract_examples_validate():
    ChooseStrategyInput.model_validate(STRATEGY_INPUT)
    ChooseStrategyResult.model_validate(STRATEGY_RESULT)
    TutorTeachingOutput.model_validate(TEACHING)
    TutorFollowUpOutput.model_validate(FOLLOW_UP)
    Level1Answer.model_validate({"result": "20.4 m", "steps": ["v = 0 at the top.", "h = 20.4 m."]})


def test_unknown_gap_type_rejected():
    with pytest.raises(ValidationError):
        TutorTeachingOutput.model_validate(bad(TEACHING, main_gap="laziness"))


def test_numeric_confidence_rejected():
    with pytest.raises(ValidationError):
        TutorTeachingOutput.model_validate(bad(TEACHING, confidence=0.7))


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        TutorTeachingOutput.model_validate(bad(TEACHING, secret="x"))


def test_non_uuid_id_rejected():
    with pytest.raises(ValidationError):
        ChooseStrategyInput.model_validate(bad(STRATEGY_INPUT, student_id="maria"))


def test_wrong_step_without_quote_rejected():
    steps = [{"role": "choose_method", "status": "wrong"}]
    with pytest.raises(ValidationError, match="quote"):
        TutorTeachingOutput.model_validate(bad(TEACHING, steps=steps))


def test_diagnosis_without_any_quote_rejected():
    steps = [{"role": "interpret", "status": "missing"}]
    with pytest.raises(ValidationError, match="quoted"):
        TutorTeachingOutput.model_validate(bad(TEACHING, steps=steps))


def test_no_steps_rejected():
    with pytest.raises(ValidationError):
        TutorTeachingOutput.model_validate(bad(TEACHING, steps=[]))


def test_empty_reply_rejected():
    with pytest.raises(ValidationError):
        TutorTeachingOutput.model_validate(bad(TEACHING, reply=""))


def test_main_gap_in_alternatives_rejected():
    with pytest.raises(ValidationError, match="main gap"):
        TutorTeachingOutput.model_validate(
            bad(TEACHING, alternatives=[{"gap": "recognition", "confidence": "low"}])
        )


def test_empty_rubric_rejected():
    data = copy.deepcopy(FOLLOW_UP)
    data["follow_up"]["hidden_rubric"] = []
    with pytest.raises(ValidationError, match="hidden_rubric"):
        TutorFollowUpOutput.model_validate(data)


def test_more_successes_than_uses_rejected():
    with pytest.raises(ValidationError):
        ChooseStrategyResult.model_validate(bad(STRATEGY_RESULT, evidence={"uses": 1, "independent_successes": 2}))
