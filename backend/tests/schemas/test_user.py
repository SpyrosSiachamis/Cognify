import copy
import json

import pytest
from pydantic import TypeAdapter, ValidationError

from app.session import schema as session
from app.tutor import schema as tutor
from app.user import schema as user

MARIA = "16e82ef2-adee-4671-8393-c6b50ac91672"
SESSION = "d96e9546-b0bf-43a7-acdc-42f43ae8adac"
CONCEPT = "44d54897-9ec4-45b9-8da1-d4ea95697d1d"
PROBLEM = "A ball is thrown vertically upward with an initial velocity of 20 m/s. How high does it go before it starts to fall? (Use g = 9.8 m/s^2)"

ANSWER_REQUEST = {"problem": PROBLEM, "subject": "physics"}
ANSWER = {
    "result": "20.4 m",
    "steps": ["At the highest point the velocity is 0 m/s.", "Use v^2 = u^2 - 2gh.",
              "Substitute: 0 = 20^2 - 2(9.8)h.", "h = 400 / 19.6 = 20.4 m."],
    "counts_as_evidence": False,
}
START_REQUEST = {"problem": PROBLEM, "subject": "physics", "student_id": MARIA, "force_experiment": False}
START = {"session_id": SESSION, "phase": "ask_first_thought",
         "message": "Before I help, what would you try first? Even an incomplete idea is useful.", "hints_used": 0}
ATTEMPT = {"text": "I found the time to the top, about 2.04 s, but I do not know how to get the height from the time."}
TEACH = {
    "session_id": SESSION, "phase": "teach",
    "message": "Let's draw it. Sketch the ball going up and mark the point where its speed becomes 0.",
    "diagnosis": {
        "steps": [
            {"role": "identify_quantities", "status": "correct", "quote": "initial velocity of 20 m/s"},
            {"role": "choose_method", "status": "wrong", "quote": "I do not know how to get the height from the time"},
        ],
        "main_gap": "recognition",
        "alternatives": [{"gap": "representation", "confidence": "low"}],
        "confidence": "medium",
    },
    "method": {"name": "visual_decomposition", "mode": "best_known", "experiment": False,
               "reason": "Worked 7 of 9 times for you on recognition gaps."},
    "hints_used": 0,
    "reply_check": {"approved": True, "summary": "No answer given. Method matches: visual_decomposition.", "outcome": "approved"},
}
STRESS = {
    "session_id": SESSION, "phase": "stress_test",
    "message": "Now I am removing the support. New problem, same underlying idea, different surface.",
    "follow_up": {"problem": "A stone is launched upward at 15 m/s from a balcony. How far above the balcony does it rise before it stops? (Use g = 9.8 m/s^2)"},
    "hints_used": 1,
    "reply_check": {"approved": True, "summary": "Follow-up keeps the principle, changes the context, does not state the answer.", "outcome": "approved"},
}
VERDICT = {
    "session_id": SESSION, "phase": "verdict", "session_over": True,
    "verdict": {
        "result": "VERIFIED",
        "evidence": "Chose the equation that needs no time and substituted correctly, with no hints on this problem.",
        "independent": True, "remaining_gap": None,
        "changes": {
            "concept": {"concept_id": CONCEPT, "name": "Constant-acceleration kinematics", "before": "fragile", "after": "verified"},
            "strategy": {"gap": "recognition", "method": "visual_decomposition",
                         "before": {"uses": 9, "independent_successes": 7},
                         "after": {"uses": 10, "independent_successes": 8}},
        },
    },
}
NOT_YET = copy.deepcopy(VERDICT)
NOT_YET.update(session_over=False, message="Not yet. Let's try a different way in.")
NOT_YET["verdict"].update(result="NOT YET", remaining_gap="recognition")
NOT_YET["verdict"]["changes"]["concept"]["after"] = "fragile"
NOT_YET["verdict"]["changes"]["strategy"]["after"] = {"uses": 10, "independent_successes": 7}
EXIT = {"phase": "exited",
        "solution": {"result": "20.4 m", "steps": ["At the highest point v = 0.", "Use v^2 = u^2 - 2gh.", "h = 400 / 19.6 = 20.4 m."]},
        "evidence_recorded": False}
LEARNER = {"student_id": MARIA, "display_name": "Maria", "is_seeded": True,
           "concepts": [{"concept_id": CONCEPT, "name": "Constant-acceleration kinematics", "state": "fragile",
                         "evidence": ["Seeded demo history: recognition gap in 3 earlier sessions."]}]}
STRATEGIES = {"student_id": MARIA, "display_name": "Maria", "is_seeded": True,
              "rows": [{"gap": "recognition", "method": "visual_decomposition", "uses": 9, "independent_successes": 7, "experiments": 0},
                       {"gap": "recognition", "method": "socratic", "uses": 5, "independent_successes": 3, "experiments": 0}],
              "methods": [{"method": "visual_decomposition", "uses": 9, "independent_successes": 7},
                          {"method": "socratic", "uses": 5, "independent_successes": 3}]}
ERROR = {"error": {"code": "model_unavailable", "message": "Please try again.", "retryable": True}}

EXAMPLES = [
    (tutor.AnswerRequest, ANSWER_REQUEST), (tutor.AnswerResponse, ANSWER),
    (session.SessionStartRequest, START_REQUEST), (session.SessionStartResponse, START),
    (session.StudentAttempt, ATTEMPT), (tutor.TutorTurn, TEACH), (tutor.TutorTurn, STRESS),
    (session.VerdictTurn, VERDICT), (session.VerdictTurn, NOT_YET), (session.ExitResponse, EXIT),
    (user.LearnerView, LEARNER), (user.StrategyView, STRATEGIES), (user.ErrorResponse, ERROR),
]


def bad(base, **changes):
    data = copy.deepcopy(base)
    data.update(changes)
    return data


@pytest.mark.parametrize("model, data", EXAMPLES)
def test_contract_examples_validate(model, data):
    model.model_validate(data)


def test_attempt_response_picks_the_right_turn():
    adapter = TypeAdapter(session.AttemptResponse)
    assert isinstance(adapter.validate_python(TEACH), tutor.TutorTurn)
    assert isinstance(adapter.validate_python(VERDICT), session.VerdictTurn)


def test_openapi_shows_examples_with_uuids():
    schema = tutor.TutorTurn.model_json_schema()
    assert schema["examples"][0]["session_id"] == SESSION


def field_names(schema):
    """Every property name anywhere in a JSON schema."""
    names = set()
    if isinstance(schema, dict):
        names |= set(schema.get("properties", {}))
        for value in schema.values():
            names |= field_names(value)
    elif isinstance(schema, list):
        for value in schema:
            names |= field_names(value)
    return names


def test_no_hidden_fields_in_any_response():
    for model in (tutor.AnswerResponse, session.SessionStartResponse, tutor.TutorTurn, session.VerdictTurn,
                  user.LearnerView, user.StrategyView, user.ErrorResponse):
        names = field_names(model.model_json_schema())
        assert not {"hidden_rubric", "hidden_solution", "solution", "verifier_notes", "note"} & names


def test_unknown_gap_type_rejected():
    data = copy.deepcopy(TEACH)
    data["diagnosis"]["main_gap"] = "laziness"
    with pytest.raises(ValidationError):
        tutor.TutorTurn.model_validate(data)


def test_numeric_confidence_rejected():
    data = copy.deepcopy(TEACH)
    data["diagnosis"]["confidence"] = 0.7
    with pytest.raises(ValidationError):
        tutor.TutorTurn.model_validate(data)


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        tutor.TutorTurn.model_validate(bad(TEACH, hidden_rubric=["x"]))


def test_non_uuid_id_rejected():
    with pytest.raises(ValidationError):
        session.SessionStartRequest.model_validate(bad(START_REQUEST, student_id="maria"))
    with pytest.raises(ValidationError):
        tutor.TutorTurn.model_validate(bad(TEACH, session_id="123"))


def test_wrong_step_without_quote_rejected():
    data = copy.deepcopy(TEACH)
    data["diagnosis"]["steps"][1].pop("quote")
    with pytest.raises(ValidationError, match="quote"):
        tutor.TutorTurn.model_validate(data)


def test_empty_message_rejected():
    with pytest.raises(ValidationError):
        tutor.TutorTurn.model_validate(bad(TEACH, message=""))
    with pytest.raises(ValidationError):
        session.StudentAttempt.model_validate({"text": ""})


def test_verified_without_independence_rejected():
    data = copy.deepcopy(VERDICT)
    data["verdict"]["independent"] = False
    with pytest.raises(ValidationError, match="independent"):
        session.VerdictTurn.model_validate(data)


def test_verified_must_end_the_session():
    with pytest.raises(ValidationError, match="ends the session"):
        session.VerdictTurn.model_validate(bad(VERDICT, session_over=False))


def test_follow_up_only_in_stress_test():
    with pytest.raises(ValidationError, match="stress_test"):
        tutor.TutorTurn.model_validate(bad(TEACH, follow_up={"problem": "x"}))
    data = copy.deepcopy(STRESS)
    data.pop("follow_up")
    with pytest.raises(ValidationError, match="stress_test"):
        tutor.TutorTurn.model_validate(data)


def test_level1_never_counts_as_evidence_and_exit_records_none():
    with pytest.raises(ValidationError):
        tutor.AnswerResponse.model_validate(bad(ANSWER, counts_as_evidence=True))
    with pytest.raises(ValidationError):
        session.ExitResponse.model_validate(bad(EXIT, evidence_recorded=True))


def test_experiment_flag_must_match_mode():
    data = copy.deepcopy(TEACH)
    data["method"]["mode"] = "experiment"
    with pytest.raises(ValidationError, match="experiment"):
        tutor.TutorTurn.model_validate(data)
