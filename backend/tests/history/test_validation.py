"""Bad values must fail loudly (no store needed)."""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.seed.data import KINEMATICS_ID, MARIA_ID
from app.history.schema import (
    AlternativeGap,
    AttemptStep,
    ConceptState,
    Diagnosis,
    FollowUp,
    Outcome,
    Student,
    VerifierCheck,
)


def outcome(**changes):
    values = dict(
        student_id=MARIA_ID,
        session_id=uuid4(),
        concept_id=KINEMATICS_ID,
        gap_type="recognition",
        method="visual_decomposition",
        decision_mode="best_known",
        result="VERIFIED",
        independent=True,
        hints_used=0,
        concept_before="fragile",
        concept_after="verified",
        evidence="Chose the equation that needs no time.",
    )
    return Outcome(**{**values, **changes})


def follow_up(**changes):
    values = dict(
        session_id=uuid4(),
        problem_text="A stone is launched upward at 15 m/s.",
        fingerprint="abc",
        concept_invariant="Choose the equation that needs no time.",
        target_gap="recognition",
        target_step="choose_method",
        perturbation="context",
        difficulty="medium",
        hidden_rubric=["Chooses v^2 = u^2 - 2gh"],
    )
    return FollowUp(**{**values, **changes})


def test_good_examples_pass():
    outcome()
    follow_up()


def test_verified_requires_independent():
    with pytest.raises(ValidationError, match="requires independent"):
        outcome(independent=False)


def test_not_yet_cannot_make_a_concept_verified():
    with pytest.raises(ValidationError, match="only on a VERIFIED"):
        outcome(result="NOT YET", independent=False)


def test_session_may_be_none_only_when_seeded():
    with pytest.raises(ValidationError, match="only for a seeded"):
        outcome(session_id=None)
    outcome(session_id=None, is_seeded=True)


def test_main_gap_not_in_alternatives():
    with pytest.raises(ValidationError, match="main gap"):
        Diagnosis(
            attempt_id=uuid4(),
            main_gap="recognition",
            alternatives=[AlternativeGap(gap="recognition", confidence="low")],
            confidence="medium",
        )


def test_follow_up_needs_a_rubric():
    with pytest.raises(ValidationError, match="hidden_rubric"):
        follow_up(hidden_rubric=[])


def test_rejected_check_needs_a_reason_and_approved_must_not_have_one():
    with pytest.raises(ValidationError, match="needs a rejection reason"):
        VerifierCheck(session_id=uuid4(), mode="reply_check", approved=False, note="x")
    with pytest.raises(ValidationError, match="must not have"):
        VerifierCheck(
            session_id=uuid4(), mode="reply_check", approved=True, reason="answer_leak", note="x"
        )
    VerifierCheck(session_id=uuid4(), mode="reply_check", approved=True, note="ok")
    VerifierCheck(
        session_id=uuid4(), mode="reply_check", approved=False, reason="answer_leak", note="x"
    )


def test_student_check_needs_its_fields():
    with pytest.raises(ValidationError, match="student check needs"):
        VerifierCheck(session_id=uuid4(), mode="student_check", approved=True, note="x")


def test_step_needs_a_quote_unless_missing():
    with pytest.raises(ValidationError, match="quote"):
        AttemptStep(attempt_id=uuid4(), position=0, role="choose_method", status="wrong")
    AttemptStep(attempt_id=uuid4(), position=1, role="interpret", status="missing")


def test_unknown_gap_type_rejected():
    with pytest.raises(ValidationError):
        outcome(gap_type="laziness")


def test_numeric_confidence_rejected():
    with pytest.raises(ValidationError):
        Diagnosis(attempt_id=uuid4(), main_gap="recognition", confidence=0.7)


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        Student(display_name="Maria", favourite_colour="blue")


def test_non_uuid_id_rejected():
    with pytest.raises(ValidationError):
        Student(id="maria", display_name="Maria")
    with pytest.raises(ValidationError):
        ConceptState(student_id="not-a-uuid", concept_id=KINEMATICS_ID, state="fragile")


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError):
        Student(display_name="Maria", created_at=datetime(2026, 1, 1))


def test_empty_text_rejected():
    with pytest.raises(ValidationError):
        Student(display_name="")


# ---- NOT YET reasons and the verified-concept rule ----


def test_a_not_yet_needs_a_reason_unless_seeded():
    with pytest.raises(ValidationError, match="needs a reason"):
        outcome(result="NOT YET", independent=False, concept_after="fragile")
    seeded = outcome(result="NOT YET", independent=False, concept_after="fragile", session_id=None, is_seeded=True)
    assert seeded.not_yet_reason is None


def test_a_verified_outcome_has_no_not_yet_reason():
    with pytest.raises(ValidationError, match="no NOT YET reason"):
        outcome(not_yet_reason="hint_limit")


def test_a_hint_limit_not_yet_may_keep_a_verified_concept_verified():
    kept = outcome(result="NOT YET", not_yet_reason="hint_limit", independent=False,
                   concept_before="verified", concept_after="verified")
    assert kept.concept_after == "verified"


@pytest.mark.parametrize("reason", ["incorrect", "not_own_work"])
def test_only_hint_limit_keeps_a_verified_concept_verified(reason):
    with pytest.raises(ValidationError, match="only on a VERIFIED result"):
        outcome(result="NOT YET", not_yet_reason=reason, independent=False,
                concept_before="verified", concept_after="verified")


def test_a_not_yet_never_moves_a_concept_into_verified():
    with pytest.raises(ValidationError, match="only on a VERIFIED result"):
        outcome(result="NOT YET", not_yet_reason="hint_limit", independent=False,
                concept_before="fragile", concept_after="verified")


def test_a_reply_draft_has_a_reason_exactly_when_the_verifier_rejected_it():
    from app.history.schema import ReplyDraft
    from uuid import uuid4

    sid = uuid4()
    assert ReplyDraft(session_id=sid, position=0, outcome="verifier_rejected", reason="method_drift").reason
    assert ReplyDraft(session_id=sid, position=0, outcome="teaching_failed", note="timeout").reason is None
    with pytest.raises(ValidationError):
        ReplyDraft(session_id=sid, position=0, outcome="verifier_rejected")
    with pytest.raises(ValidationError):
        ReplyDraft(session_id=sid, position=0, outcome="approved", reason="answer_leak")
    with pytest.raises(ValidationError):
        ReplyDraft(session_id=sid, position=0, outcome="turn_failed")
