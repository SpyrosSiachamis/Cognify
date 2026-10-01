"""The session fields and reads the user module relies on."""

from app.history.schema import Attempt, Diagnosis, FollowUp, Problem, Session, SessionSolution, StrategyDecision
from app.seed.data import KINEMATICS_ID, MARIA_ID

from tests.history.test_store import fingerprint, outcome_for, start_session


def test_session_defaults_and_hidden_solution(store):
    session = start_session(store)
    assert (session.status, session.teach_turns, session.not_yet_count) == ("active", 0, 0)
    assert session.hidden_solution is None and session.force_experiment is False
    problem = store.add_problem(Problem(text="p", fingerprint=fingerprint("p")))
    solved = store.create_session(
        Session(
            student_id=MARIA_ID,
            problem_id=problem.id,
            hidden_solution=SessionSolution(result="20.4 m", steps=["h = 400 / 19.6"]),
        )
    )
    assert store.get_session(solved.id).hidden_solution.result == "20.4 m"
    assert store.get_problem(problem.id).text == "p"


def test_get_concept(store):
    assert store.get_concept(KINEMATICS_ID).name == "Constant-acceleration kinematics"
    concept = store.get_or_create_concept("Fractions")
    assert store.get_concept(concept.id).name == "Fractions"
    assert store.get_concept(session_id_that_does_not_exist()) is None


def session_id_that_does_not_exist():
    from uuid import uuid4

    return uuid4()


def test_latest_reads_return_the_newest_record(store):
    session = start_session(store)
    assert store.latest_diagnosis(session.id) is None
    assert store.latest_strategy_decision(session.id) is None
    assert store.latest_follow_up(session.id) is None

    for gap in ("recognition", "procedure"):
        attempt = Attempt(session_id=session.id, phase="teach", text="x")
        store.add_attempt(attempt, [])
        store.add_diagnosis(Diagnosis(attempt_id=attempt.id, main_gap=gap, confidence="medium"))
        store.add_strategy_decision(
            StrategyDecision(
                session_id=session.id, gap_type=gap, method="socratic",
                decision_mode="best_known", reason="r", uses=1, independent_successes=1,
            )
        )
        store.add_follow_up(
            FollowUp(
                session_id=session.id, problem_text=gap, fingerprint=fingerprint(gap),
                concept_invariant="c", target_gap=gap, target_step="choose_method",
                perturbation="context", difficulty="medium", hidden_rubric=["r"],
            )
        )
    assert store.latest_diagnosis(session.id).main_gap == "procedure"
    assert store.latest_strategy_decision(session.id).gap_type == "procedure"
    assert store.latest_follow_up(session.id).problem_text == "procedure"


def test_record_verdict_sets_the_session_status_when_over(store):
    session = start_session(store)
    store.record_verdict(outcome_for(session), session_over=True)
    assert store.get_session(session.id).status == "verified"

    other = start_session(store)
    store.record_verdict(
        outcome_for(other, result="NOT YET", before="verified", after="fragile"), session_over=False
    )
    assert store.get_session(other.id).status == "active"
