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

| Model | 14 cases (×3) | General + verifier (×3) | Matrix diagnosis: unfinished, not wrong | Notes |
|---|---|---|---|---|
| `mistral.mistral-large-3-675b-instruct` | 37/42 | 98/99 | 7/7 valid samples (1 timeout); gap named `concept` in 3/7 | Current default. |
| `deepseek.v3.2` | pending | pending | 1/1 (smoke test) | Diagnosis call about 21 s. |

The matrix column samples the reasoning step alone on the matrix attempt in `scripts/scenarios.py`: the
individual products must be `correct`, the summation `missing`, with no `wrong` step and no error.

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
