"""The tutor pipeline offline: reason -> rules -> repair -> choose -> teach -> verify.

Each test names the architectural invariant it protects.
"""

import asyncio

import pytest

from app.ai_gateway import gateway
from app.seed.data import MARIA_ID, NIKOS_ID
from app.tutor.agent import MAX_REGENERATIONS, AgentTutor, final_answers
from app.tutor.language import ACKNOWLEDGE_REPLY, FALLBACK_REPLY, student_language, written_in
from app.tutor.repair import assess_repair, gap_step, repaired
from app.tutor.schema import DimensionRating, PriorDiagnosis, Step, TutorDiagnosis
from app.tutor.strategy import choose_strategy

from .conftest import MARIA_FIRST_THOUGHT, SOLUTION, teach_request
from .fakes import APPROVE, HEAVY, FakeVerifier, ScriptedModel, diagnosis

STALL = diagnosis(
    ("compute", "correct", "about 2.04 s"),
    ("choose_method", "missing", "I don't know how to get the height from the time"),
    gap="recognition",
)
CORRECT = diagnosis(
    ("identify_quantities", "correct", "At the highest point, v = 0"),
    ("compute", "correct", "h = 20.4 m"),
    gap="transfer",  # the model invents a gap; the rules must remove it
)
NOTHING = diagnosis(("choose_method", "missing", None), gap="concept", confidence="high")


def run(store, model, verifier=None, request=None, **kwargs):
    tutor = AgentTutor(store, model.model, (verifier or FakeVerifier()).model, **kwargs)
    result = asyncio.run(tutor.teach(request or teach_request()))
    return tutor, result


# ---- diagnosis invariance ----


def test_reasoning_sees_the_work_only(store):
    model = ScriptedModel([STALL])
    run(store, model)
    sent = model.reasoning_inputs[0]
    assert set(sent) == {"problem", "attempt", "final_answer"}  # no strategy, history or solution route


def test_changing_the_strategy_does_not_change_the_diagnosis(store):
    plain, forced = ScriptedModel([STALL]), ScriptedModel([STALL])
    _, best = run(store, plain)
    _, experiment = run(store, forced, request=teach_request(force_experiment=True))
    assert best.method.method != experiment.method.method
    assert best.output.model_dump(exclude={"reply"}) == experiment.output.model_dump(exclude={"reply"})


def test_regeneration_reruns_teaching_only(store):
    model = ScriptedModel([STALL], replies=["Too much help.", "What do you know at the top?"])
    _, result = run(store, model, FakeVerifier(HEAVY, APPROVE))
    assert model.reasoning_calls == 1 and len(model.teaching_inputs) == 2
    assert model.teaching_inputs[1]["retry_reason"] == "heavy_hint"
    assert model.teaching_inputs[1]["diagnosis"] == model.teaching_inputs[0]["diagnosis"]
    assert result.output.reply == "What do you know at the top?"


def test_teaching_is_aimed_at_the_gap_step(store):
    model = ScriptedModel([STALL])
    tutor, _ = run(store, model)
    sent = model.teaching_inputs[0]
    assert sent["mode"] == "teach"
    assert sent["gap_step"]["role"] == "choose_method"
    assert sent["strategy"]["method"] == "visual_decomposition"
    assert tutor.last_trace.strategy.reason == "Worked 7 of 9 times for you on recognition gaps."


# ---- no gap ----


def test_correct_work_has_no_gap_and_no_teaching(store):
    model, verifier = ScriptedModel([CORRECT]), FakeVerifier()
    tutor, result = run(store, model, verifier, request=teach_request("At the highest point, v = 0, so h = 20.4 m."))
    assert result.output.main_gap is None
    assert result.method is None
    assert model.teaching_calls == 0 and verifier.inputs == []
    assert result.output.reply == ACKNOWLEDGE_REPLY["English"] and tutor.last_trace.mode == "acknowledge"


# ---- insufficient evidence ----


def test_no_reasoning_is_insufficient_and_gets_a_probe(store):
    model = ScriptedModel([NOTHING], replies=["Where would you start with this problem?"])
    tutor, result = run(store, model, request=teach_request("I don't know."))
    out = result.output
    assert (out.evidence, out.confidence, out.main_gap) == ("insufficient", "low", None)
    assert result.method is None
    assert model.teaching_inputs[0]["mode"] == "probe" and model.teaching_inputs[0]["strategy"] is None
    assert result.output.reply == "Where would you start with this problem?"


def test_no_reasoning_after_teaching_keeps_teaching_the_same_gap(store):
    prior = PriorDiagnosis(steps=[Step(role="choose_method", status="missing")], main_gap="recognition")
    model = ScriptedModel([NOTHING])
    tutor, result = run(store, model, request=teach_request("I still don't know.", first_thought=False, prior=prior))
    assert result.output.main_gap == "recognition" and result.output.confidence == "low"
    assert result.method.method == "visual_decomposition"
    assert model.teaching_inputs[0]["gap_step"]["role"] == "choose_method"
    assert not result.output.gap_repaired


# ---- repair evidence (code, not the model) ----

MISSING = Step(role="choose_method", status="missing")
WRONG = Step(role="choose_method", status="wrong", quote="v times t")
RIGHT = Step(role="choose_method", status="correct", quote="v^2 = u^2 - 2gh")
OTHER = Step(role="compute", status="correct", quote="2.04 s")


def reading(*steps: Step, gap: str | None = "procedure", dims: list[tuple[str, str]] = ()) -> TutorDiagnosis:
    """The model's reading of the current turn, for the repair check."""
    return TutorDiagnosis(steps=list(steps), main_gap=gap, confidence="medium",
                          dimensions=[DimensionRating(name=n, state=st, evidence="x") for n, st in dims])


STALLED = PriorDiagnosis(steps=[OTHER, MISSING], main_gap="recognition")


@pytest.mark.parametrize(
    ("prior", "now", "expected"),
    [
        (STALLED, reading(OTHER, RIGHT, gap=None), True),
        (PriorDiagnosis(steps=[WRONG], main_gap="concept"),
         reading(RIGHT, Step(role="compute", status="missing"), gap="procedure"), True),
        (STALLED, reading(OTHER, MISSING, gap="recognition"), False),
        (PriorDiagnosis(steps=[MISSING], main_gap=None), reading(RIGHT, gap=None), False),
        (None, reading(RIGHT, gap=None), False),
    ],
    ids=["missing->correct", "wrong->correct", "still-missing", "no-prior-gap", "no-prior"],
)
def test_repair_compares_the_gap_step(prior, now, expected):
    assert repaired(prior, now) is expected


def test_genuine_repair_names_the_new_evidence():
    check = assess_repair(STALLED, reading(OTHER, RIGHT, gap=None))
    assert check.repaired and "v^2 = u^2 - 2gh" in check.reason


def test_model_labels_the_gap_step_correct_but_still_finds_the_same_gap():
    mislabelled = Step(role="choose_method", status="correct", quote="At the top the speed is 0")
    check = assess_repair(STALLED, reading(OTHER, mislabelled, gap="recognition"))
    assert not check.repaired and check.reason.startswith("conflict")


def test_correct_label_on_last_turns_evidence_is_not_repair():
    prior = PriorDiagnosis(steps=[OTHER, Step(role="choose_method", status="wrong", quote="2.04 s")],
                           main_gap="recognition")
    relabelled = Step(role="choose_method", status="correct", quote="2.04 s")
    check = assess_repair(prior, reading(relabelled, gap=None))
    assert not check.repaired and "already gave" in check.reason


def test_correct_label_on_not_knowing_is_not_repair():
    unsure = Step(role="choose_method", status="correct", quote="I'm not sure which equation")
    assert not repaired(STALLED, reading(OTHER, unsure, gap=None))


def test_a_different_step_demonstrated_is_not_repair():
    quantities_now = Step(role="identify_quantities", status="correct", quote="u = 20, v = 0")
    check = assess_repair(STALLED, reading(quantities_now, OTHER, MISSING, gap="recognition"))
    assert not check.repaired and "choose_method is still missing" in check.reason


def test_partial_improvement_is_not_repair():
    check = assess_repair(STALLED, reading(OTHER, RIGHT, gap="procedure", dims=[("recognition", "fragile")]))
    assert not check.repaired and check.reason.startswith("partial")


def test_gap_step_follows_the_kind_of_gap():
    quantities = Step(role="identify_quantities", status="missing")
    assert gap_step([quantities, OTHER, MISSING], "recognition").role == "choose_method"
    assert gap_step([quantities, OTHER, MISSING], None).role == "identify_quantities"


def test_an_unlisted_gap_step_counts_as_missing():
    steps = [Step(role="identify_quantities", status="missing"), OTHER]
    assert (gap_step(steps, "recognition").role, gap_step(steps, "recognition").status) == ("choose_method", "missing")


def test_listing_quantities_does_not_repair_a_recognition_gap():
    prior = PriorDiagnosis(steps=[Step(role="identify_quantities", status="missing"), OTHER, MISSING],
                           main_gap="recognition")
    now = reading(Step(role="identify_quantities", status="correct", quote="u = 20"), OTHER, MISSING, gap="recognition")
    assert not repaired(prior, now)


def test_gap_step_prefers_the_first_wrong_step():
    assert gap_step([MISSING, OTHER, Step(role="interpret", status="wrong", quote="x")]).role == "interpret"
    assert gap_step([OTHER, MISSING]).role == "choose_method"
    assert gap_step([OTHER]) is None


def test_a_repaired_gap_is_acknowledged_not_retaught(store):
    prior = PriorDiagnosis(steps=[MISSING], main_gap="recognition")
    now = diagnosis(("choose_method", "correct", "h = ut + 1/2 at^2"), ("substitute", "missing", None), gap="procedure")
    model = ScriptedModel([now])
    _, result = run(store, model, request=teach_request("h = ut + 1/2 at^2, so I can use u = 20.", prior=prior))
    assert result.output.gap_repaired and model.teaching_calls == 0


# ---- choose_strategy ----


def test_choose_strategy_uses_observed_history(store):
    best = choose_strategy(store, MARIA_ID, "recognition")
    assert (best.method, best.mode, best.evidence.uses, best.evidence.independent_successes) == (
        "visual_decomposition", "best_known", 9, 7)
    cold = choose_strategy(store, MARIA_ID, "concept")
    assert cold.mode == "cold_start" and cold.evidence.uses == 0
    experiment = choose_strategy(store, MARIA_ID, "recognition", force_experiment=True)
    assert experiment.mode == "experiment" and experiment.method == "micro_hint"  # untried P0 method
    assert "Trying something different" in experiment.reason
    assert choose_strategy(store, NIKOS_ID, "procedure").method == "worked_example"


# ---- verification boundary and answer leakage ----


def test_only_an_approved_reply_reaches_the_student(store):
    model = ScriptedModel([STALL], replies=["Too much help."])
    tutor, result = run(store, model, FakeVerifier(HEAVY))
    assert len(tutor.last_trace.drafts) == 1 + MAX_REGENERATIONS
    assert result.output.reply == FALLBACK_REPLY["English"] and not result.reply_check.approved


def test_code_catches_a_leaked_answer_before_the_verifier(store):
    model = ScriptedModel([STALL], replies=["So h = 20.4 m!", "What do you know at the top?"])
    verifier = FakeVerifier()
    tutor, result = run(store, model, verifier)
    assert tutor.last_trace.drafts[0].check.reason == "answer_leak"
    assert len(verifier.inputs) == 1  # only the clean draft reached the verifier model
    assert "20.4" not in result.output.reply


def test_leak_check_covers_the_bare_number():
    assert final_answers(SOLUTION) == ["20.4 m", "20.4"]


def test_a_failing_verifier_never_lets_a_reply_through(store):
    model = ScriptedModel([STALL])
    _, result = run(store, model, FakeVerifier({"mode": "reply_check", "approved": "maybe"}))
    assert result.output.reply == FALLBACK_REPLY["English"] and not result.reply_check.approved


# ---- invalid output, provider errors and timeouts (gateway) ----


@pytest.mark.parametrize(
    "broken",
    [
        {k: v for k, v in STALL.items() if k != "confidence"},
        {**STALL, "main_gap": "laziness"},
        {**STALL, "steps": "all of them"},
        {**STALL, "steps": [{"role": "compute", "status": "wrong", "quote": "about 2.04 s"}], "main_gap": None},
    ],
    ids=["missing-field", "invalid-enum", "wrong-type", "wrong-step-without-gap"],
)
def test_invalid_diagnosis_twice_becomes_a_probe_not_a_crash(store, broken):
    model = ScriptedModel([broken])
    tutor, result = run(store, model)
    assert model.reasoning_calls == 2  # one retry
    assert tutor.last_trace.diagnosis_failure.startswith("invalid_output")
    assert result.output.evidence == "insufficient" and tutor.last_trace.mode == "probe"


def test_invalid_diagnosis_once_is_retried(store):
    model = ScriptedModel([{**STALL, "main_gap": "laziness"}, STALL])
    _, result = run(store, model)
    assert model.reasoning_calls == 2 and result.output.main_gap == "recognition"


def test_timeout_falls_back(store):
    model = ScriptedModel([STALL], delay=1)
    tutor, result = run(store, model, timeout=0.05)
    assert tutor.last_trace.diagnosis_failure.startswith("timeout")
    assert result.output.reply == FALLBACK_REPLY["English"]


def test_gateway_maps_failures_to_typed_fallbacks():
    from pydantic_ai import Agent
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.models.function import FunctionModel

    def provider_down(messages, info):
        raise ModelHTTPError(status_code=503, model_name="x", body="down")

    agent = Agent(output_type=str)
    result = asyncio.run(gateway.call(agent, "hi", model=FunctionModel(provider_down), fallback="safe"))
    assert (result.ok, result.failure, result.value) == (False, "provider_error", "safe")


# ---- reasoning rules ----


def test_invented_quote_becomes_missing(store):
    invented = diagnosis(
        ("identify_quantities", "correct", "A ball is thrown upward at 20 m/s"),
        ("compute", "correct", "about 2.04 s"),
        ("choose_method", "missing", None),
    )
    _, result = run(store, ScriptedModel([invented]))
    steps = {s.role: (s.status, s.quote) for s in result.output.steps}
    assert steps["identify_quantities"] == ("missing", None)
    assert steps["compute"] == ("correct", "about 2.04 s")


def test_saying_you_do_not_know_is_missing_not_wrong(store):
    marked_wrong = diagnosis(
        ("compute", "correct", "about 2.04 s"),
        ("choose_method", "wrong", "I don't know how to get the height from the time"),
    )
    _, result = run(store, ScriptedModel([marked_wrong]))
    step = next(s for s in result.output.steps if s.role == "choose_method")
    assert step.status == "missing" and step.quote == "I don't know how to get the height from the time"


def test_a_gap_must_show_at_its_step(store):
    contradictory = diagnosis(("choose_method", "correct", "about 2.04 s"), ("interpret", "missing", None),
                              gap="recognition")
    model = ScriptedModel([contradictory, STALL])
    _, result = run(store, model)
    assert model.reasoning_calls == 2  # sent back once with the reason
    assert result.output.main_gap == "recognition"


def test_a_gap_step_disagreement_is_accepted_on_the_retry(store):
    contradictory = diagnosis(("choose_method", "correct", "about 2.04 s"), ("interpret", "missing", None),
                              gap="recognition")
    model = ScriptedModel([contradictory, contradictory])
    tutor, result = run(store, model)
    assert model.reasoning_calls == 2 and tutor.last_trace.diagnosis_failure is None
    assert result.output.main_gap == "recognition"  # kept, not replaced by a probe


def test_maria_first_thought_text_is_the_attempt(store):
    model = ScriptedModel([STALL])
    run(store, model)
    assert model.reasoning_inputs[0]["attempt"] == MARIA_FIRST_THOUGHT
    assert model.reasoning_inputs[0]["final_answer"] == "20.4 m"


# ---- the student's language ----


def test_language_detection():
    assert student_language("I found the time, but not the height.") == "English"
    assert student_language("v^2 = u^2 - 2gh, so h = 20.4 m") == "English"
    assert student_language("Βρήκα τον χρόνο αλλά όχι το ύψος.") == "Greek"
    assert written_in("What do you know at the very top?", "English")
    assert not written_in("Tu as bien trouvé le temps pour atteindre le sommet !", "English")
    assert not written_in("Τι ξέρεις στην κορυφή;", "English")
    assert written_in("Τι ξέρεις για την ταχύτητα στην κορυφή;", "Greek")


def test_a_reply_in_the_wrong_language_is_regenerated_before_the_verifier(store):
    model = ScriptedModel([STALL], replies=["Tu as bien trouvé le temps ! Que sais-tu au sommet ?",
                                            "You found the time. What do you know at the very top?"])
    verifier = FakeVerifier()
    tutor, result = run(store, model, verifier)
    assert tutor.last_trace.drafts[0].failure.startswith("language")
    assert len(verifier.inputs) == 1  # the French draft never reached the verifier
    assert model.teaching_inputs[0]["language"] == "English"
    assert "English" in model.teaching_inputs[1]["retry_note"]
    assert result.output.reply == "You found the time. What do you know at the very top?"


def test_a_greek_student_is_taught_in_greek(store):
    model = ScriptedModel([diagnosis(("compute", "correct", "περίπου 2.04 s"), ("choose_method", "missing", None))],
                          replies=["Τι ξέρεις για την ταχύτητα στην κορυφή;"])
    _, result = run(store, model, request=teach_request("Βρήκα τον χρόνο, περίπου 2.04 s, αλλά όχι το ύψος."))
    assert model.teaching_inputs[0]["language"] == "Greek"
    assert result.output.reply == "Τι ξέρεις για την ταχύτητα στην κορυφή;"


# ---- method adherence (case 08): the verifier gets the contract, rejection reruns teaching only ----

DRIFT = {"mode": "reply_check", "approved": False, "reason": "method_drift",
         "note": "The method needs the student to lay out knowns and the unknown; this is a plain question."}
OFF_TARGET = {"mode": "reply_check", "approved": False, "reason": "off_target",
              "note": "Aim at connecting her time to the height, not at the topic in general."}


def test_verifier_receives_gap_method_definition_and_language(store):
    verifier = FakeVerifier()
    run(store, ScriptedModel([STALL]), verifier)
    sent = verifier.inputs[0]
    assert sent["main_gap"] == "recognition"
    assert sent["gap_step"].startswith("choose_method (missing)")
    assert "lay the situation out in parts" in sent["method_definition"]
    assert sent["language"] == "English"


@pytest.mark.parametrize("rejection", [DRIFT, OFF_TARGET], ids=["method_drift", "off_target"])
def test_drift_or_off_target_regenerates_teaching_with_the_reason(store, rejection):
    model = ScriptedModel([STALL], replies=["What do you think comes next?", "List what you know at launch and at the top."])
    tutor, result = run(store, model, FakeVerifier(rejection, APPROVE))
    assert model.reasoning_calls == 1 and len(model.teaching_inputs) == 2
    assert model.teaching_inputs[1]["retry_reason"] == rejection["reason"]
    assert model.teaching_inputs[1]["retry_note"] == rejection["note"]
    assert result.output.reply == "List what you know at launch and at the top."


def test_persistent_drift_ends_in_the_fallback(store):
    model = ScriptedModel([STALL], replies=["What do you think comes next?"])
    tutor, result = run(store, model, FakeVerifier(DRIFT))
    assert [d.check.reason for d in tutor.last_trace.drafts] == ["method_drift"] * (1 + MAX_REGENERATIONS)
    assert result.output.reply == FALLBACK_REPLY["English"] and not result.reply_check.approved


def test_a_probe_has_no_method_contract(store):
    verifier = FakeVerifier()
    run(store, ScriptedModel([NOTHING], replies=["Where would you start?"]), verifier, request=teach_request("I don't know."))
    assert verifier.inputs[0]["method"] is None and verifier.inputs[0]["method_definition"] is None


def test_missing_steps_with_real_reasoning_keep_the_gap(store):
    # Every step missing, but one carries the student's actual reasoning: still a diagnosis, not a probe.
    reasoning_on_a_missing_step = diagnosis(
        ("choose_method", "missing", "I found the time to the top, about 2.04 s, but I don't know how to get the height"),
        ("compute", "missing", None),
        gap="recognition",
    )
    tutor, result = run(store, ScriptedModel([reasoning_on_a_missing_step]))
    assert result.output.evidence == "sufficient" and result.output.main_gap == "recognition"
    assert tutor.last_trace.mode == "teach"


def test_only_not_knowing_is_still_insufficient(store):
    only_unsure = diagnosis(("choose_method", "missing", "I still don't know"), gap="recognition", confidence="high")
    tutor, result = run(store, ScriptedModel([only_unsure]), request=teach_request("I still don't know."))
    assert result.output.evidence == "insufficient" and tutor.last_trace.mode == "probe"
