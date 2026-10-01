"""Test-plan cases that need pieces that are not built yet. Kept visible as skips."""

import pytest

NOT_BUILT = {
    "case_14_not_yet_path": "needs real follow-up generation and the student check (M4); the stub judges today",
    "case_15_lucky_correct_answer_is_not_verified": "needs the real student check (M4, F16); code's hint cap exists in SessionService",
    "case_16_fresh_problem_transfer": "needs follow-up generation (M4, F14/F15)",
    "case_17_same_principle_different_representation": "needs follow-up generation with a representation perturbation (M4)",
    "case_18_experiment_vs_best_known": "needs the full exploration rules (F12); only force_experiment exists",
    "case_19_level_1_isolation": "needs the Level 1 answer path (F3)",
    "case_20_end_to_end_master_loop": "needs real set_up, follow_up and judge (the stub answers them today)",
}


@pytest.mark.parametrize("case", NOT_BUILT.keys())
def test_not_built_yet(case):
    pytest.skip(f"{case}: {NOT_BUILT[case]}")
