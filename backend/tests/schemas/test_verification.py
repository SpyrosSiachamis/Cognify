import pytest
from pydantic import ValidationError

from app.verification.schema import VerifierResultAdapter, StudentCheckResult

REJECTED = {"mode": "reply_check", "approved": False, "reason": "answer_leak", "note": "The reply states the final height."}
STUDENT = {"mode": "student_check", "correct": True, "reasoning_quality": "strong", "own_work": True,
           "note": "Used the time-free equation; hint count is decided by code."}


def test_contract_examples_validate():
    assert VerifierResultAdapter.validate_python(REJECTED).mode == "reply_check"
    assert isinstance(VerifierResultAdapter.validate_python(STUDENT), StudentCheckResult)
    VerifierResultAdapter.validate_python({"mode": "follow_up_check", "approved": True, "note": "Same principle."})


def test_rejected_without_reason_rejected():
    with pytest.raises(ValidationError, match="needs a rejection reason"):
        VerifierResultAdapter.validate_python({"mode": "reply_check", "approved": False, "note": "x"})


def test_approved_with_reason_rejected():
    with pytest.raises(ValidationError, match="must not have"):
        VerifierResultAdapter.validate_python({**REJECTED, "approved": True})


def test_unknown_mode_and_reason_rejected():
    with pytest.raises(ValidationError):
        VerifierResultAdapter.validate_python({**REJECTED, "mode": "vibes_check"})
    with pytest.raises(ValidationError):
        VerifierResultAdapter.validate_python({**REJECTED, "reason": "boredom"})


def test_extra_field_rejected_and_no_verified_decision_field():
    with pytest.raises(ValidationError):
        VerifierResultAdapter.validate_python({**STUDENT, "verified": True})


def test_numeric_quality_rejected():
    with pytest.raises(ValidationError):
        VerifierResultAdapter.validate_python({**STUDENT, "reasoning_quality": 0.9})


def test_student_check_needs_its_fields():
    data = {k: v for k, v in STUDENT.items() if k != "own_work"}
    with pytest.raises(ValidationError):
        VerifierResultAdapter.validate_python(data)
