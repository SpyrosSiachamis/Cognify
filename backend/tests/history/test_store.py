import hashlib
from datetime import timedelta
from uuid import uuid4

from app.seed.data import KINEMATICS_ID, MARIA_ID, NIKOS_ID
from app.history.schema import (
    Attempt,
    FollowUp,
    Outcome,
    Problem,
    Session,
    now,
)


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()


def stats(store, student_id):
    return {(s.gap_type, s.method): s for s in store.strategy_stats(student_id)}


def start_session(store, student_id=MARIA_ID, text="A ball is thrown up at 20 m/s."):
    problem = store.add_problem(Problem(text=text, fingerprint=fingerprint(text)))
    return store.create_session(Session(student_id=student_id, problem_id=problem.id))


def outcome_for(session, result="VERIFIED", before="fragile", after="verified", mode="best_known"):
    verified = result == "VERIFIED"
    return Outcome(
        student_id=session.student_id,
        session_id=session.id,
        concept_id=KINEMATICS_ID,
        gap_type="recognition",
        method="visual_decomposition",
        decision_mode=mode,
        result=result,
        independent=verified,
        hints_used=0 if verified else 3,
        concept_before=before,
        concept_after=after,
        evidence="Chose the equation that needs no time.",
    )


# ---- seed ----


def test_seeded_stats_maria(store):
    s = stats(store, MARIA_ID)
    assert (s["recognition", "visual_decomposition"].uses, s["recognition", "visual_decomposition"].independent_successes) == (9, 7)
    assert (s["recognition", "worked_example"].uses, s["recognition", "worked_example"].independent_successes) == (7, 4)
    assert (s["recognition", "socratic"].uses, s["recognition", "socratic"].independent_successes) == (5, 3)
    assert not any(method in ("analogy", "counterexample") for _, method in s)


def test_seeded_stats_nikos(store):
    s = stats(store, NIKOS_ID)
    assert [(k, v.uses, v.independent_successes) for k, v in sorted(s.items())] == [
        (("procedure", "socratic"), 3, 1),
        (("procedure", "visual_decomposition"), 4, 2),
        (("procedure", "worked_example"), 6, 5),
    ]


def test_maria_last_success_about_six_days_ago(store):
    last = stats(store, MARIA_ID)["recognition", "visual_decomposition"].last_success_at
    assert timedelta(days=5) < now() - last < timedelta(days=7)


def test_other_methods_succeeded_within_30_days(store):
    for key in [("recognition", "worked_example"), ("recognition", "socratic")]:
        assert now() - stats(store, MARIA_ID)[key].last_success_at < timedelta(days=30)


def test_gap_type_filter(store):
    assert store.strategy_stats(MARIA_ID, gap_type="procedure") == []
    assert len(store.strategy_stats(MARIA_ID, gap_type="recognition")) == 3


def test_load_seed_twice_changes_nothing(store):
    from app.seed import seed_store

    seed_store(store)
    assert stats(store, MARIA_ID)["recognition", "visual_decomposition"].uses == 9


# ---- verdict ----


def test_verified_verdict_updates_stats_and_concept(store):
    session = start_session(store)
    state = store.record_verdict(outcome_for(session))
    s = stats(store, MARIA_ID)["recognition", "visual_decomposition"]
    assert (s.uses, s.independent_successes) == (10, 8)
    assert state.state == "verified"
    assert store.get_concept_state(MARIA_ID, KINEMATICS_ID).state == "verified"
    assert store.get_session(session.id).phase == "verdict"
    assert store.get_session(session.id).ended_at is not None


def test_not_yet_adds_a_use_but_no_success(store):
    session = start_session(store)
    store.record_verdict(outcome_for(session, "NOT YET", after="fragile"), session_over=False)
    s = stats(store, MARIA_ID)["recognition", "visual_decomposition"]
    assert (s.uses, s.independent_successes) == (10, 7)
    assert store.get_concept_state(MARIA_ID, KINEMATICS_ID).state == "fragile"
    assert store.get_session(session.id).ended_at is None


def test_verdict_with_wrong_concept_before_writes_nothing(store):
    session = start_session(store)
    bad = outcome_for(session, before="weak")  # stored state is fragile
    try:
        store.record_verdict(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    assert stats(store, MARIA_ID)["recognition", "visual_decomposition"].uses == 9
    assert store.get_session(session.id).phase == "ask_first_thought"


def test_experiments_count_only_experiment_decisions(store):
    session = start_session(store)
    store.record_verdict(outcome_for(session, mode="experiment"), session_over=False)
    store.record_verdict(
        outcome_for(session, before="verified", after="verified", mode="best_known")
    )
    s = stats(store, MARIA_ID)["recognition", "visual_decomposition"]
    assert (s.uses, s.experiments) == (11, 1)


# ---- fingerprints ----


def test_seen_fingerprints_for_that_student_only(store):
    session = start_session(store, MARIA_ID, "Ball problem for Maria")
    store.add_follow_up(
        FollowUp(
            session_id=session.id,
            problem_text="A stone is launched upward at 15 m/s.",
            fingerprint=fingerprint("stone"),
            concept_invariant="Choose the equation that needs no time.",
            target_gap="recognition",
            target_step="choose_method",
            perturbation="context",
            difficulty="medium",
            hidden_rubric=["Chooses v^2 = u^2 - 2gh"],
        )
    )
    start_session(store, NIKOS_ID, "Ball problem for Nikos")
    maria = {(f.kind, f.fingerprint) for f in store.seen_fingerprints(MARIA_ID)}
    nikos = {(f.kind, f.fingerprint) for f in store.seen_fingerprints(NIKOS_ID)}
    assert maria == {
        ("problem", fingerprint("Ball problem for Maria")),
        ("follow_up", fingerprint("stone")),
    }
    assert nikos == {("problem", fingerprint("Ball problem for Nikos"))}


# ---- copies ----


def test_returned_objects_are_copies(store):
    student = store.get_student(MARIA_ID)
    student.display_name = "Changed"
    assert store.get_student(MARIA_ID).display_name == "Maria"

    state = store.get_concept_state(MARIA_ID, KINEMATICS_ID)
    state.evidence.append("tampered")
    assert "tampered" not in store.get_concept_state(MARIA_ID, KINEMATICS_ID).evidence

    session = start_session(store)
    session.phase = "teach"
    assert store.get_session(session.id).phase == "ask_first_thought"


def test_input_objects_are_copied_on_write(store):
    session = start_session(store)
    changed = session.model_copy(update={"hints_used": 2})
    store.update_session(changed)
    changed.hints_used = 99
    assert store.get_session(session.id).hints_used == 2


def test_get_or_create_concept_is_idempotent(store):
    first = store.get_or_create_concept("Constant-acceleration kinematics")
    again = store.get_or_create_concept("  constant-acceleration KINEMATICS ")
    assert first.id == again.id == KINEMATICS_ID
    assert store.get_or_create_concept("Energy").id != KINEMATICS_ID


# ---- reset ----


def test_reset_demo(store):
    session = start_session(store)
    store.add_attempt(Attempt(session_id=session.id, phase="ask_first_thought", text="I tried"), [])
    store.record_verdict(outcome_for(session))
    store.reset_demo()
    store.reset_demo()  # running it twice is safe

    assert store.get_session(session.id) is None
    assert store.list_attempts(session.id) == []
    s = stats(store, MARIA_ID)["recognition", "visual_decomposition"]
    assert (s.uses, s.independent_successes) == (9, 7)
    state = store.get_concept_state(MARIA_ID, KINEMATICS_ID)
    assert state.state == "fragile" and state.is_seeded
    assert stats(store, NIKOS_ID)["procedure", "worked_example"].uses == 6
    assert store.seen_fingerprints(MARIA_ID) == []
