# Model evaluation log

Which Bedrock model runs the tutor (`TUTOR_MODEL_ID`) is a configuration choice, so the same suites are run on
each candidate and recorded here. Only on-demand models work on this account (inference profiles are blocked).

How to add a run:

```bash
# 14 cases, 3 parallel runs; --log also appends the table to backend/eval_runs.md (copy it into Runs below)
docker compose exec -e TUTOR_MODEL_ID=<model> backend python -m scripts.eval_live --runs 3 --log eval_runs.md
# generalization and verifier suites (record the pass counts by hand)
docker compose exec -e TUTOR_MODEL_ID=<model> backend python -m pytest -m live \
    tests/tutor/test_general_live.py tests/tutor/test_verifier_live.py -q
```

Run suites one model at a time: parallel streams against one account slow every call and cause timeouts.

## Summary

Same tutor code (commit `a2d2554`), prompts, schemas, validation, retries and verifier for every model; only
`TUTOR_MODEL_ID` changed. One model serves every LLM step. Full per-run data: `docs/evaluation_results.json`
(summary tables in `docs/EVALUATION_DATA.md`). Small samples (3 runs per test): read these as tendencies, not a ranking.

| Model | 14 cases (×3) | General (×3) | Verifier (×3) | Matrix probe | Case 13 repair probe |
|---|---|---|---|---|---|
| `mistral.mistral-large-3-675b-instruct` | 37 / 42 = 88.1% | 53 / 54 = 98.1% | 45 / 45 = 100.0% | 12 / 14 = 85.7% | 3 / 8 = 37.5% |
| `deepseek.v3.2` | 28 / 42 = 66.7% | 34 / 54 = 63.0% | 45 / 45 = 100.0% | 7 / 14 = 50.0% | 3 / 8 = 37.5% |
| `qwen.qwen3-next-80b-a3b` | 32 / 42 = 76.2% | 46 / 54 = 85.2% | 43 / 45 = 95.6% | 12 / 14 = 85.7% | 8 / 8 = 100.0% |

What the failures were (counts over all five suites):

| Model | Main failure kinds |
|---|---|
| Mistral Large 3 | Diagnosis 6, assertion without detail 3, timeout 2, API retry error 1, method drift 1. Spread thin; no case fails in all 3 runs. |
| DeepSeek V3.2 | Structured output 25 (its diagnosis output fails validation after 2 retries, so the turn falls back to a probe), diagnosis 12, timeout 4. Slowest: a 14-case run took 8 to 11 min. |
| Qwen3 Next 80B A3B | Diagnosis 13 (case 08: the gap changes between identical inputs; "correct answer, wrong explanation" missed 3/3), verification 5 (case 10 rejects the heavy hint but labels it `method_drift`; a named-but-not-performed counterexample approved twice), structured output 3. Fastest: about 3 min per run. |

The matrix probe samples the reasoning step alone on the matrix attempt in `scripts/scenarios.py`: the
individual products must not be called wrong, and no error may be stated. The case 13 probe runs case 13's
diagnosis and the code repair check: the student's found equation must count as repairing the gap.

## Runs

### 2026-10-01 · mistral.mistral-large-3-675b-instruct · 14 cases

| Case | Run 1 | Run 2 | Run 3 | Pass rate |
|---|---|---|---|---|
| case_01_wrong_reasoning_is_found_and_not_praised | pass | pass | pass | 3/3 |
| case_02_partial_reasoning_credits_the_time_and_finds_the_stall | pass | pass | pass | 3/3 |
| case_03_correct_work_gets_no_invented_gap | pass | pass | pass | 3/3 |
| case_03_correct_work_moves_toward_the_stress_test | pass | pass | FAIL | 2/3 |
| case_04_wrong_displacement_method_is_pinpointed | pass | pass | FAIL | 2/3 |
| case_05_no_reasoning_gets_a_probe_not_a_label | pass | pass | pass | 3/3 |
| case_06_velocity_zero_is_not_acceleration_zero | pass | FAIL | pass | 2/3 |
| case_07_correct_work_beats_a_recognition_history | pass | pass | pass | 3/3 |
| case_08_strategy_changes_the_move_not_the_diagnosis | pass | pass | FAIL | 2/3 |
| case_09_stuck_student_gets_scaffolding_not_the_answer | pass | pass | pass | 3/3 |
| case_09_verifier_rejects_a_leak_written_in_words | pass | pass | pass | 3/3 |
| case_10_verifier_rejects_a_heavy_hint | pass | pass | pass | 3/3 |
| case_13_student_finds_the_equation_and_the_gap_is_repaired | FAIL | pass | pass | 2/3 |
| case_14_student_still_stuck_is_not_repaired | pass | pass | pass | 3/3 |
| **total** | 13/14 | 13/14 | 11/14 | 37/42 |

- run 3 case_03_correct_work_moves_toward_the_stress_test: app.user.errors.ApiError: Please try again.
- run 3 case_04_wrong_displacement_method_is_pinpointed: assert False
- run 2 case_06_velocity_zero_is_not_acceleration_zero: assert None
- run 3 case_08_strategy_changes_the_move_not_the_diagnosis: AssertionError: worked_example: no draft passed the method-adherence check
- run 1 case_13_student_finds_the_equation_and_the_gap_is_repaired: assert False

wall time 265s for 3 parallel runs (each run finished after: 265s / 265s / 265s)

### 2026-10-01 · mistral.mistral-large-3-675b-instruct · general + verifier

- run 1: 32/33 (failed: test_correct_work_that_stops_is_unfinished_not_wrong[mean]: the reasoning call timed out after 45 s, so the turn fell back to a probe)
- run 2: 33/33
- run 3: 33/33

### 2026-10-01 · deepseek.v3.2 · 14 cases

| Case | Run 1 | Run 2 | Run 3 | Pass rate |
|---|---|---|---|---|
| case_01_wrong_reasoning_is_found_and_not_praised | FAIL | FAIL | FAIL | 0/3 |
| case_02_partial_reasoning_credits_the_time_and_finds_the_stall | pass | pass | FAIL | 2/3 |
| case_03_correct_work_gets_no_invented_gap | pass | pass | pass | 3/3 |
| case_03_correct_work_moves_toward_the_stress_test | pass | pass | pass | 3/3 |
| case_04_wrong_displacement_method_is_pinpointed | FAIL | FAIL | FAIL | 0/3 |
| case_05_no_reasoning_gets_a_probe_not_a_label | pass | pass | pass | 3/3 |
| case_06_velocity_zero_is_not_acceleration_zero | FAIL | FAIL | FAIL | 0/3 |
| case_07_correct_work_beats_a_recognition_history | pass | pass | pass | 3/3 |
| case_08_strategy_changes_the_move_not_the_diagnosis | FAIL | FAIL | pass | 1/3 |
| case_09_stuck_student_gets_scaffolding_not_the_answer | pass | pass | pass | 3/3 |
| case_09_verifier_rejects_a_leak_written_in_words | pass | pass | pass | 3/3 |
| case_10_verifier_rejects_a_heavy_hint | FAIL | FAIL | pass | 1/3 |
| case_13_student_finds_the_equation_and_the_gap_is_repaired | pass | pass | pass | 3/3 |
| case_14_student_still_stuck_is_not_repaired | pass | pass | pass | 3/3 |
| **total** | 9/14 | 9/14 | 10/14 | 28/42 |

- run 1 case_01_wrong_reasoning_is_found_and_not_praised: AssertionError: assert 'wrong' in ['missing']
- run 2 case_01_wrong_reasoning_is_found_and_not_praised: AssertionError: assert 'wrong' in ['missing']
- run 3 case_01_wrong_reasoning_is_found_and_not_praised: AssertionError: assert 'wrong' in ['missing']
- run 3 case_02_partial_reasoning_credits_the_time_and_finds_the_stall: AssertionError: assert (True and 'socratic' == 'visual_decomposition'
- run 1 case_04_wrong_displacement_method_is_pinpointed: assert False
- run 2 case_04_wrong_displacement_method_is_pinpointed: assert False
- run 3 case_04_wrong_displacement_method_is_pinpointed: assert False
- run 1 case_06_velocity_zero_is_not_acceleration_zero: assert None == 'concept'
- run 2 case_06_velocity_zero_is_not_acceleration_zero: assert None == 'concept'
- run 3 case_06_velocity_zero_is_not_acceleration_zero: assert None == 'concept'
- run 1 case_08_strategy_changes_the_move_not_the_diagnosis: AttributeError: 'NoneType' object has no attribute 'method'
- run 2 case_08_strategy_changes_the_move_not_the_diagnosis: AttributeError: 'NoneType' object has no attribute 'method'
- run 1 case_10_verifier_rejects_a_heavy_hint: AssertionError: assert False
- run 2 case_10_verifier_rejects_a_heavy_hint: AssertionError: assert False

wall time 668s for 3 parallel runs (each run finished after: 498s / 668s / 668s)

### 2026-10-01 · deepseek.v3.2 · general + verifier

- run 1: 7 failed, 26 passed; failed: test_general_live.py::test_algebra_good_method_arithmetic_slip test_general_live.py::test_other_kinematics_problem_wrong_method test_general_live.py::test_correct_answer_wrong_explanation test_general_live.py::test_real_problems_still_get_a_diagnosis[right-answer-wrong-reason] test_general_live.py::test_real_problems_still_get_a_diagnosis[conceptual-error] test_general_live.py::test_correct_work_that_stops_is_unfinished_not_wrong[matrix] test_general_live.py::test_correct_work_that_stops_is_unfinished_not_wrong[kinematics] 
- run 2: 7 failed, 26 passed; failed: test_general_live.py::test_algebra_good_method_arithmetic_slip test_general_live.py::test_other_kinematics_problem_wrong_method test_general_live.py::test_correct_answer_wrong_explanation test_general_live.py::test_real_problems_still_get_a_diagnosis[right-answer-wrong-reason] test_general_live.py::test_real_problems_still_get_a_diagnosis[incomplete] test_general_live.py::test_real_problems_still_get_a_diagnosis[conceptual-error] test_general_live.py::test_correct_work_that_stops_is_unfinished_not_wrong[matrix] 
- run 3: 6 failed, 27 passed; failed: test_general_live.py::test_algebra_good_method_arithmetic_slip test_general_live.py::test_other_kinematics_problem_wrong_method test_general_live.py::test_correct_answer_wrong_explanation test_general_live.py::test_correct_work_gets_no_invented_gap[concise] test_general_live.py::test_real_problems_still_get_a_diagnosis[right-answer-wrong-reason] test_general_live.py::test_real_problems_still_get_a_diagnosis[conceptual-error] 

### 2026-10-01 · qwen.qwen3-next-80b-a3b · 14 cases

| Case | Run 1 | Run 2 | Run 3 | Pass rate |
|---|---|---|---|---|
| case_01_wrong_reasoning_is_found_and_not_praised | pass | pass | pass | 3/3 |
| case_02_partial_reasoning_credits_the_time_and_finds_the_stall | FAIL | pass | FAIL | 1/3 |
| case_03_correct_work_gets_no_invented_gap | pass | pass | pass | 3/3 |
| case_03_correct_work_moves_toward_the_stress_test | pass | pass | FAIL | 2/3 |
| case_04_wrong_displacement_method_is_pinpointed | pass | pass | pass | 3/3 |
| case_05_no_reasoning_gets_a_probe_not_a_label | pass | pass | pass | 3/3 |
| case_06_velocity_zero_is_not_acceleration_zero | pass | pass | FAIL | 2/3 |
| case_07_correct_work_beats_a_recognition_history | pass | pass | pass | 3/3 |
| case_08_strategy_changes_the_move_not_the_diagnosis | FAIL | FAIL | FAIL | 0/3 |
| case_09_stuck_student_gets_scaffolding_not_the_answer | pass | pass | pass | 3/3 |
| case_09_verifier_rejects_a_leak_written_in_words | pass | pass | pass | 3/3 |
| case_10_verifier_rejects_a_heavy_hint | FAIL | FAIL | FAIL | 0/3 |
| case_13_student_finds_the_equation_and_the_gap_is_repaired | pass | pass | pass | 3/3 |
| case_14_student_still_stuck_is_not_repaired | pass | pass | pass | 3/3 |
| **total** | 11/14 | 12/14 | 9/14 | 32/42 |

- run 1 case_02_partial_reasoning_credits_the_time_and_finds_the_stall: assert False
- run 3 case_02_partial_reasoning_credits_the_time_and_finds_the_stall: assert 'representation' in ('recognition', 'strategy_choice')
- run 3 case_03_correct_work_moves_toward_the_stress_test: app.user.errors.ApiError: Please try again.
- run 3 case_06_velocity_zero_is_not_acceleration_zero: assert False
- run 1 case_08_strategy_changes_the_move_not_the_diagnosis: AssertionError: diagnosis changed between runs: {'visual_decomposition': 'recognition', 'socratic': 'recognition', 'worked_example': 'representation'}
- run 2 case_08_strategy_changes_the_move_not_the_diagnosis: AssertionError: diagnosis changed between runs: {'visual_decomposition': 'representation', 'socratic': 'recognition', 'worked_example': 'recognition'}
- run 3 case_08_strategy_changes_the_move_not_the_diagnosis: AssertionError: diagnosis changed between runs: {'visual_decomposition': 'representation', 'socratic': 'recognition', 'worked_example': 'recognition'}
- run 1 case_10_verifier_rejects_a_heavy_hint: assert (not False and 'method_drift' in ('heavy_hint', 'answer_leak'))
- run 2 case_10_verifier_rejects_a_heavy_hint: assert (not False and 'method_drift' in ('heavy_hint', 'answer_leak'))
- run 3 case_10_verifier_rejects_a_heavy_hint: assert (not False and 'method_drift' in ('heavy_hint', 'answer_leak'))

wall time 452s for 3 parallel runs (each run finished after: 179s / 179s / 452s)

### 2026-10-01 · qwen.qwen3-next-80b-a3b · general + verifier

- run 1: 4 failed, 29 passed; failed: test_general_live.py::test_algebra_partial_reasoning test_general_live.py::test_correct_answer_wrong_explanation test_general_live.py::test_real_problems_still_get_a_diagnosis[incomplete] test_verifier_live.py::test_naming_a_method_without_performing_it_is_rejected[fractions-counterexample] 
- run 2: 3 failed, 30 passed; failed: test_general_live.py::test_correct_answer_wrong_explanation test_general_live.py::test_correct_work_that_stops_is_unfinished_not_wrong[matrix] test_verifier_live.py::test_naming_a_method_without_performing_it_is_rejected[fractions-counterexample] 
- run 3: 3 failed, 30 passed; failed: test_general_live.py::test_correct_answer_wrong_explanation test_general_live.py::test_correct_work_gets_no_invented_gap[complete] test_general_live.py::test_real_problems_still_get_a_diagnosis[incomplete] 
