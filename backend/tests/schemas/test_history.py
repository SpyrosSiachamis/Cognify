"""History records (app/services/history/schema.py): the contract's values and the bad examples."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.seed.data import KINEMATICS_ID, MARIA_ID
from app.services.history.schema import (
    AlternativeGap,
    AttemptStep,
    Diagnosis,
    FollowUp,
    Outcome,
    Student,
    VerifierCheck,
)


def outcome(**changes):
    values = dict(
        student_id=MARIA_ID, session_id=uuid4(), concept_id=KINEMATICS_ID,
        gap_type="recognition", method="visual_decomposition", decision_mode="best_known",
        result="VERIFIED", independent=True, hints_used=0,
        concept_before="fragile", concept_after="verified", evidence="Chose the time-free equation.",
    )
    return Outcome(**{**values, **changes})


def test_contract_style_records_validate():
    outcome()
    Student(id=MARIA_ID, display_name="Maria", is_seeded=True)
    AttemptStep(attempt_id=uuid4(), position=0, role="choose_method", status="wrong", quote="I do not know")
    Diagnosis(attempt_id=uuid4(), main_gap="recognition", confidence="medium",
              alternatives=[AlternativeGap(gap="representation", confidence="low")])


def test_unknown_gap_type_rejected():
    with pytest.raises(ValidationError):
        outcome(gap_type="laziness")


def test_numeric_confidence_rejected():
    with pytest.raises(ValidationError):
        Diagnosis(attempt_id=uuid4(), main_gap="recognition", confidence=0.7)


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        Student(display_name="Maria", colour="blue")


def test_non_uuid_id_rejected():
    with pytest.raises(ValidationError):
        Student(id="maria", display_name="Maria")


def test_wrong_step_without_quote_rejected():
    with pytest.raises(ValidationError, match="quote"):
        AttemptStep(attempt_id=uuid4(), position=0, role="choose_method", status="wrong")


def test_verified_without_independence_rejected():
    with pytest.raises(ValidationError, match="independent"):
        outcome(independent=False)


def test_session_none_only_when_seeded():
    with pytest.raises(ValidationError):
        outcome(session_id=None)


def test_main_gap_in_alternatives_rejected():
    with pytest.raises(ValidationError):
        Diagnosis(attempt_id=uuid4(), main_gap="recognition", confidence="low",
                  alternatives=[AlternativeGap(gap="recognition", confidence="low")])


def test_empty_rubric_rejected():
    with pytest.raises(ValidationError):
        FollowUp(session_id=uuid4(), problem_text="p", fingerprint="f", concept_invariant="c",
                 target_gap="recognition", target_step="choose_method", perturbation="context",
                 difficulty="medium", hidden_rubric=[])


def test_rejected_check_without_reason_rejected():
    with pytest.raises(ValidationError):
        VerifierCheck(session_id=uuid4(), mode="reply_check", approved=False, note="x")
