# Evaluation data

Human-readable summary of `docs/evaluation_results.json`, which holds every individual observation (one per test per run, or per probe sample). All numbers below are computed from those observations; nothing is estimated. No ranking is implied: these are small samples (3 runs per test) of stochastic systems.

## Conditions

| | |
|---|---|
| only model id changed | yes |
| same cognify code | yes |
| same prompts | yes |
| same schemas | yes |
| same validation | yes |
| same retry and repair logic | yes |
| same verifier | yes |
| same test cases | yes |
| tutor code | commit `a2d2554` for every run |
| models | Mistral Large 3 (`mistral.mistral-large-3-675b-instruct`), DeepSeek V3.2 (`deepseek.v3.2`), Qwen3 Next 80B A3B (`qwen.qwen3-next-80b-a3b`) |
| provider | AWS Bedrock, on-demand inference, us-east-1 |
| run order | Models were run one after the other (Mistral, DeepSeek, Qwen), except that a single Qwen smoke call ran during DeepSeek's 14-case run. Within a model: the 14-case suite (3 runs in parallel), then general + verifier (3 runs in parallel), then the probes. |
| measurement differences | Only in what was recorded, not in what ran: Qwen's runs kept junit files (per-test times) and DeepSeek's 14-case junit files were copied during the run; the Mistral runs kept none. The probe scripts for DeepSeek and Qwen add a latency field; their diagnosis logic is the same as for Mistral. |

## Model evaluation

| Model | Suite | Passed | Total | Pass rate |
| ----- | ----- | -----: | ----: | --------: |
| Mistral Large 3 | 14 cases | 37 | 42 | 88.1% |
| Mistral Large 3 | General | 53 | 54 | 98.1% |
| Mistral Large 3 | Verifier | 45 | 45 | 100.0% |
| Mistral Large 3 | General + verifier | 98 | 99 | 99.0% |
| Mistral Large 3 | Matrix diagnosis probe | 12 | 14 | 85.7% |
| Mistral Large 3 | Case 13 repair probe | 3 | 8 | 37.5% |
| DeepSeek V3.2 | 14 cases | 28 | 42 | 66.7% |
| DeepSeek V3.2 | General | 34 | 54 | 63.0% |
| DeepSeek V3.2 | Verifier | 45 | 45 | 100.0% |
| DeepSeek V3.2 | General + verifier | 79 | 99 | 79.8% |
| DeepSeek V3.2 | Matrix diagnosis probe | 7 | 14 | 50.0% |
| DeepSeek V3.2 | Case 13 repair probe | 3 | 8 | 37.5% |
| Qwen3 Next 80B A3B | 14 cases | 32 | 42 | 76.2% |
| Qwen3 Next 80B A3B | General | 46 | 54 | 85.2% |
| Qwen3 Next 80B A3B | Verifier | 43 | 45 | 95.6% |
| Qwen3 Next 80B A3B | General + verifier | 89 | 99 | 89.9% |
| Qwen3 Next 80B A3B | Matrix diagnosis probe | 12 | 14 | 85.7% |
| Qwen3 Next 80B A3B | Case 13 repair probe | 8 | 8 | 100.0% |

Runs: 3 per test for the 14 cases, general and verifier suites. The probes are ad-hoc scripts (not in the repo), counted per sample: 14 matrix samples and 8 case 13 samples per model.

## Domain evaluation

A/B suites only. Domains not tested: Biology, History, Programming, Chemistry, Logic / critical reasoning (no results are shown for them).

| Domain | Model | Passed | Total | Pass rate |
| ------ | ----- | -----: | ----: | --------: |
| Mathematics | Mistral Large 3 | 71 | 74 | 95.9% |
| Mathematics | DeepSeek V3.2 | 55 | 74 | 74.3% |
| Mathematics | Qwen3 Next 80B A3B | 64 | 74 | 86.5% |
| Physics | Mistral Large 3 | 79 | 89 | 88.8% |
| Physics | DeepSeek V3.2 | 62 | 89 | 69.7% |
| Physics | Qwen3 Next 80B A3B | 77 | 89 | 86.5% |

## Capability evaluation

Primary: each test counts once, under the capability it is named for. All tags: a test also counts under each secondary capability it asserts; a test's pass or fail is not split per assertion, so a failure counts against all its tags.

### Primary capability (each test counted once)

| Capability | Model | Passed | Total | Pass rate |
| ---------- | ----- | -----: | ----: | --------: |
| Correct vs incorrect distinction | Mistral Large 3 | 26 | 27 | 96.3% |
| Correct vs incorrect distinction | DeepSeek V3.2 | 14 | 27 | 51.9% |
| Correct vs incorrect distinction | Qwen3 Next 80B A3B | 26 | 27 | 96.3% |
| Gap repair detection | Mistral Large 3 | 8 | 14 | 57.1% |
| Gap repair detection | DeepSeek V3.2 | 9 | 14 | 64.3% |
| Gap repair detection | Qwen3 Next 80B A3B | 14 | 14 | 100.0% |
| Incomplete vs wrong distinction | Mistral Large 3 | 32 | 35 | 91.4% |
| Incomplete vs wrong distinction | DeepSeek V3.2 | 23 | 35 | 65.7% |
| Incomplete vs wrong distinction | Qwen3 Next 80B A3B | 27 | 35 | 77.1% |
| Independent-work detection | Mistral Large 3 | 6 | 6 | 100.0% |
| Independent-work detection | DeepSeek V3.2 | 6 | 6 | 100.0% |
| Independent-work detection | Qwen3 Next 80B A3B | 6 | 6 | 100.0% |
| Insufficient-evidence handling | Mistral Large 3 | 9 | 9 | 100.0% |
| Insufficient-evidence handling | DeepSeek V3.2 | 9 | 9 | 100.0% |
| Insufficient-evidence handling | Qwen3 Next 80B A3B | 9 | 9 | 100.0% |
| Misconception detection | Mistral Large 3 | 11 | 12 | 91.7% |
| Misconception detection | DeepSeek V3.2 | 0 | 12 | 0.0% |
| Misconception detection | Qwen3 Next 80B A3B | 8 | 12 | 66.7% |
| No answer leak | Mistral Large 3 | 3 | 3 | 100.0% |
| No answer leak | DeepSeek V3.2 | 3 | 3 | 100.0% |
| No answer leak | Qwen3 Next 80B A3B | 3 | 3 | 100.0% |
| Problem setup | Mistral Large 3 | 3 | 3 | 100.0% |
| Problem setup | DeepSeek V3.2 | 3 | 3 | 100.0% |
| Problem setup | Qwen3 Next 80B A3B | 3 | 3 | 100.0% |
| Teaching-method adherence | Mistral Large 3 | 38 | 39 | 97.4% |
| Teaching-method adherence | DeepSeek V3.2 | 37 | 39 | 94.9% |
| Teaching-method adherence | Qwen3 Next 80B A3B | 34 | 39 | 87.2% |
| Transfer follow-up | Mistral Large 3 | 5 | 6 | 83.3% |
| Transfer follow-up | DeepSeek V3.2 | 6 | 6 | 100.0% |
| Transfer follow-up | Qwen3 Next 80B A3B | 5 | 6 | 83.3% |
| Verification | Mistral Large 3 | 9 | 9 | 100.0% |
| Verification | DeepSeek V3.2 | 7 | 9 | 77.8% |
| Verification | Qwen3 Next 80B A3B | 6 | 9 | 66.7% |

### All tags (a test also counts under the capabilities it asserts secondarily)

| Capability | Model | Passed | Total | Pass rate |
| ---------- | ----- | -----: | ----: | --------: |
| Correct vs incorrect distinction | Mistral Large 3 | 28 | 30 | 93.3% |
| Correct vs incorrect distinction | DeepSeek V3.2 | 17 | 30 | 56.7% |
| Correct vs incorrect distinction | Qwen3 Next 80B A3B | 28 | 30 | 93.3% |
| Diagnosis without a misconception claim | Mistral Large 3 | 12 | 14 | 85.7% |
| Diagnosis without a misconception claim | DeepSeek V3.2 | 7 | 14 | 50.0% |
| Diagnosis without a misconception claim | Qwen3 Next 80B A3B | 12 | 14 | 85.7% |
| Evidence grounding | Mistral Large 3 | 30 | 33 | 90.9% |
| Evidence grounding | DeepSeek V3.2 | 14 | 33 | 42.4% |
| Evidence grounding | Qwen3 Next 80B A3B | 28 | 33 | 84.8% |
| Gap repair detection | Mistral Large 3 | 8 | 14 | 57.1% |
| Gap repair detection | DeepSeek V3.2 | 9 | 14 | 64.3% |
| Gap repair detection | Qwen3 Next 80B A3B | 14 | 14 | 100.0% |
| Incomplete vs wrong distinction | Mistral Large 3 | 32 | 35 | 91.4% |
| Incomplete vs wrong distinction | DeepSeek V3.2 | 23 | 35 | 65.7% |
| Incomplete vs wrong distinction | Qwen3 Next 80B A3B | 27 | 35 | 77.1% |
| Independent-work detection | Mistral Large 3 | 9 | 9 | 100.0% |
| Independent-work detection | DeepSeek V3.2 | 9 | 9 | 100.0% |
| Independent-work detection | Qwen3 Next 80B A3B | 9 | 9 | 100.0% |
| Insufficient-evidence handling | Mistral Large 3 | 9 | 9 | 100.0% |
| Insufficient-evidence handling | DeepSeek V3.2 | 9 | 9 | 100.0% |
| Insufficient-evidence handling | Qwen3 Next 80B A3B | 9 | 9 | 100.0% |
| Language (Greek) | Mistral Large 3 | 3 | 3 | 100.0% |
| Language (Greek) | DeepSeek V3.2 | 3 | 3 | 100.0% |
| Language (Greek) | Qwen3 Next 80B A3B | 3 | 3 | 100.0% |
| Misconception detection | Mistral Large 3 | 11 | 12 | 91.7% |
| Misconception detection | DeepSeek V3.2 | 0 | 12 | 0.0% |
| Misconception detection | Qwen3 Next 80B A3B | 8 | 12 | 66.7% |
| No answer leak | Mistral Large 3 | 14 | 15 | 93.3% |
| No answer leak | DeepSeek V3.2 | 9 | 15 | 60.0% |
| No answer leak | Qwen3 Next 80B A3B | 14 | 15 | 93.3% |
| Problem setup | Mistral Large 3 | 3 | 3 | 100.0% |
| Problem setup | DeepSeek V3.2 | 3 | 3 | 100.0% |
| Problem setup | Qwen3 Next 80B A3B | 3 | 3 | 100.0% |
| Teaching targeting | Mistral Large 3 | 3 | 3 | 100.0% |
| Teaching targeting | DeepSeek V3.2 | 0 | 3 | 0.0% |
| Teaching targeting | Qwen3 Next 80B A3B | 3 | 3 | 100.0% |
| Teaching-method adherence | Mistral Large 3 | 41 | 42 | 97.6% |
| Teaching-method adherence | DeepSeek V3.2 | 39 | 42 | 92.9% |
| Teaching-method adherence | Qwen3 Next 80B A3B | 35 | 42 | 83.3% |
| Transfer follow-up | Mistral Large 3 | 5 | 6 | 83.3% |
| Transfer follow-up | DeepSeek V3.2 | 6 | 6 | 100.0% |
| Transfer follow-up | Qwen3 Next 80B A3B | 5 | 6 | 83.3% |
| Verification | Mistral Large 3 | 56 | 57 | 98.2% |
| Verification | DeepSeek V3.2 | 53 | 57 | 93.0% |
| Verification | Qwen3 Next 80B A3B | 49 | 57 | 86.0% |

## Failure categories

A/B suites. Meanings are in `failure_taxonomy` in the JSON.

| Failure category | Mistral Large 3 | DeepSeek V3.2 | Qwen3 Next 80B A3B |
| ---------------- | ----: | ----: | ----: |
| Infrastructure/API | 1 | 0 | 0 |
| Timeout | 2 | 4 | 1 |
| Structured output | 0 | 25 | 3 |
| Diagnosis | 6 | 12 | 13 |
| Teaching-method drift | 1 | 0 | 0 |
| Verification | 0 | 0 | 5 |
| Assertion/test expectation | 3 | 2 | 0 |
| Other | 0 | 3 | 0 |

## Individual runs: 14 cases

Each run kept separately (stochasticity).

| Case | Mistral Large 3 | DeepSeek V3.2 | Qwen3 Next 80B A3B |
| ---- | --- | --- | --- |
| case_01_wrong_reasoning_is_found_and_not_praised | PASS PASS PASS | FAIL FAIL FAIL | PASS PASS PASS |
| case_02_partial_reasoning_credits_the_time_and_finds_the_stall | PASS PASS PASS | PASS PASS FAIL | FAIL PASS FAIL |
| case_03_correct_work_gets_no_invented_gap | PASS PASS PASS | PASS PASS PASS | PASS PASS PASS |
| case_03_correct_work_moves_toward_the_stress_test | PASS PASS FAIL | PASS PASS PASS | PASS PASS FAIL |
| case_04_wrong_displacement_method_is_pinpointed | PASS PASS FAIL | FAIL FAIL FAIL | PASS PASS PASS |
| case_05_no_reasoning_gets_a_probe_not_a_label | PASS PASS PASS | PASS PASS PASS | PASS PASS PASS |
| case_06_velocity_zero_is_not_acceleration_zero | PASS FAIL PASS | FAIL FAIL FAIL | PASS PASS FAIL |
| case_07_correct_work_beats_a_recognition_history | PASS PASS PASS | PASS PASS PASS | PASS PASS PASS |
| case_08_strategy_changes_the_move_not_the_diagnosis | PASS PASS FAIL | FAIL FAIL PASS | FAIL FAIL FAIL |
| case_09_stuck_student_gets_scaffolding_not_the_answer | PASS PASS PASS | PASS PASS PASS | PASS PASS PASS |
| case_09_verifier_rejects_a_leak_written_in_words | PASS PASS PASS | PASS PASS PASS | PASS PASS PASS |
| case_10_verifier_rejects_a_heavy_hint | PASS PASS PASS | FAIL FAIL PASS | FAIL FAIL FAIL |
| case_13_student_finds_the_equation_and_the_gap_is_repaired | FAIL PASS PASS | PASS PASS PASS | PASS PASS PASS |
| case_14_student_still_stuck_is_not_repaired | PASS PASS PASS | PASS PASS PASS | PASS PASS PASS |

## Notes

- Latency: latency_seconds is the test's (or probe sample's) duration where it was recorded: DeepSeek's 14-case runs (junit files saved during the run), all of Qwen's suites, and the DeepSeek and Qwen probes. It is null for every Mistral observation and for DeepSeek's general and verifier runs, because those runs kept no per-test times. Tests ran 3 at a time in parallel, so a duration includes waiting on the account's shared throughput. run_wall_seconds is a whole run's wall time.
- DeepSeek V3.2: most of its general-suite failures are structured output (its diagnosis output failed validation after 2 retries, so the turn fell back to a probe) or timeouts, not wrong diagnoses. Six of its 14-case failures have the shape the safe fallback produces; their logs cannot show whether a fallback happened, and each such observation says so in its notes.
- Development reruns (Mistral only, recorded but outside the comparison): dev_rerun_targeted_cases.
- 498 observations in total.
