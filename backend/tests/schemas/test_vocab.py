from app.common import vocab


def test_glossary_values_match_the_contract():
    assert vocab.values(vocab.Phase) == ("ask_first_thought", "teach", "stress_test", "verdict", "exited")
    assert vocab.values(vocab.GapType) == (
        "recognition", "representation", "concept", "procedure",
        "strategy_choice", "self_correction", "transfer",
    )
    assert vocab.values(vocab.Strategy) == (
        "socratic", "visual_decomposition", "worked_example", "analogy",
        "counterexample", "representation_switch", "micro_hint",
    )
    assert vocab.values(vocab.DecisionMode) == ("best_known", "experiment", "cold_start")
    assert vocab.values(vocab.StepRole) == (
        "identify_quantities", "choose_method", "set_up", "substitute", "compute", "interpret",
    )
    assert vocab.values(vocab.StepStatus) == ("correct", "wrong", "missing")
    assert vocab.values(vocab.State) == ("strong", "fragile", "weak", "untested", "verified")
    assert vocab.values(vocab.Confidence) == ("low", "medium", "high")
    assert vocab.values(vocab.VerdictResult) == ("VERIFIED", "NOT YET")
    assert vocab.values(vocab.VerifierMode) == ("reply_check", "follow_up_check", "student_check")
    assert vocab.values(vocab.RejectionReason) == (
        "answer_leak", "heavy_hint", "method_drift", "off_target", "shaming_tone", "invalid_followup", "not_independent",
    )


def test_nine_dimensions_and_rating_scale():
    assert len(vocab.values(vocab.Dimension)) == 9
    assert vocab.values(vocab.Rating) == ("strong", "fragile", "weak", "untested")


def test_every_rating_is_a_state():
    assert set(vocab.values(vocab.Rating)) < set(vocab.values(vocab.State))


def test_session_status_values():
    assert vocab.values(vocab.SessionStatus) == ("active", "verified", "not_yet_ended", "exited")
