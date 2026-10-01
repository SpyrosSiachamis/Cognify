# Cross-domain evaluation v2

A hand-written benchmark of Cognify's reasoning, diagnosis and tutoring behaviour: 70 cases, 7 domains x 10 reasoning patterns, with adversarial traps. It tests whether Cognify can tell what a student has actually shown from what is incomplete, locally wrong, conceptually wrong or unsupported. It does **not** measure educational effectiveness, and no single accuracy number is given: every rate names its numerator, denominator, checks and number of cases. One run per case: small per-cell samples (a domain or pattern row is 10 or 7 cases).

## Run

- Model: Mistral Large 3 (`mistral.mistral-large-3-675b-instruct`); one run per case, no reruns; started 2026-10-01T20:53:45+00:00.
- Code: HEAD `a748bfa`; tutor code (`backend/app`) uncommitted changes: none; v2 files SHA-256 recorded in the JSON.
- Entry point: AgentTutor.set_up then AgentTutor.teach_with_trace. Offline validation before the run: 369 passed (tests/tutor/test_cross_domain_v2_cases.py), no model calls.
- Cases: `backend/tests/tutor/cross_domain_cases_v2.py`; runner: `backend/tests/tutor/test_cross_domain_v2_live.py`. Quotes are matched ignoring case and spaces; step roles are never part of a check.

## Overall

| Check set | Passed | Total | Pass rate |
| --------- | -----: | ----: | --------: |
| All checks (diagnosis and tutoring) | 42 | 70 | 60.0% |
| Diagnosis checks only | 54 | 70 | 77.1% |
| Tutoring checks only (no leak, approved reply) | 53 | 70 | 75.7% |

Units are cases. A case passes a check set when every check of that set that applies to it passes.

## By domain

| Domain | Cases | All checks | Diagnosis only |
| ------ | ----: | ---------: | -------------: |
| Mathematics | 10 | 6 / 10 = 60.0% | 7 / 10 = 70.0% |
| Physics | 10 | 5 / 10 = 50.0% | 9 / 10 = 90.0% |
| Biology | 10 | 7 / 10 = 70.0% | 8 / 10 = 80.0% |
| History | 10 | 7 / 10 = 70.0% | 8 / 10 = 80.0% |
| Programming | 10 | 5 / 10 = 50.0% | 7 / 10 = 70.0% |
| Chemistry | 10 | 7 / 10 = 70.0% | 8 / 10 = 80.0% |
| Logic / critical reasoning | 10 | 5 / 10 = 50.0% | 7 / 10 = 70.0% |

## By pattern

| Pattern | Cases | All checks | Diagnosis only |
| ------- | ----: | ---------: | -------------: |
| incomplete_early_stop | 7 | 5 / 7 = 71.4% | 7 / 7 = 100.0% |
| incomplete_implicit_step | 7 | 0 / 7 = 0.0% | 0 / 7 = 0.0% |
| incorrect_conceptual | 7 | 7 / 7 = 100.0% | 7 / 7 = 100.0% |
| incorrect_local_error | 7 | 0 / 7 = 0.0% | 4 / 7 = 57.1% |
| correct_answer_wrong_reasoning | 7 | 7 / 7 = 100.0% | 7 / 7 = 100.0% |
| correct_reasoning_wrong_answer | 7 | 0 / 7 = 0.0% | 4 / 7 = 57.1% |
| correct_work | 7 | 7 / 7 = 100.0% | 7 / 7 = 100.0% |
| no_reasoning | 7 | 6 / 7 = 85.7% | 6 / 7 = 85.7% |
| misconception | 7 | 5 / 7 = 71.4% | 6 / 7 = 85.7% |
| repair_followup | 7 | 5 / 7 = 71.4% | 6 / 7 = 85.7% |

## By trap

| Trap | Cases | All checks |
| ---- | ----: | ---------: |
| A: correct answer + invalid reasoning | 7 | 7 / 7 = 100.0% |
| B: wrong answer + mostly valid reasoning | 7 | 0 / 7 = 0.0% |
| C: correct reasoning + wrong final transcription | 7 | 0 / 7 = 0.0% |
| D: lucky guess | 7 | 6 / 7 = 85.7% |
| E: confidence trap | 4 | 4 / 4 = 100.0% |
| F: uncertainty trap | 3 | 3 / 3 = 100.0% |
| G: partial repair | 2 | 0 / 2 = 0.0% |
| H: false repair | 2 | 2 / 2 = 100.0% |
| I: several valid steps then one wrong step | 4 | 0 / 4 = 0.0% |
| J: evidence localization | 7 | 5 / 7 = 71.4% |

## By capability

Units are check instances (one check on one case). Each row names its check set and case set.

| Capability | Part | Passed / total | Cases | Checks | Case set |
| ---------- | ---- | -------------: | ----: | ------ | -------- |
| Correct vs incorrect distinction | false claims flagged | 66 / 70 = 94.3% | 35 | error_stated, marks_the_error_wrong | correct_answer_wrong_reasoning, correct_reasoning_wrong_answer, incorrect_conceptual, incorrect_local_error, misconception |
| Correct vs incorrect distinction | correct work not flagged | 7 / 7 = 100.0% | 7 | no_step_wrong | correct_work |
| Incomplete vs incorrect distinction |  | 14 / 28 = 50.0% | 14 | no_error_stated, no_step_wrong | incomplete_early_stop, incomplete_implicit_step |
| Evidence grounding | valid work credited with its quote | 28 / 33 = 84.8% | 33 | credits_valid_work | all patterns |
| Evidence grounding | false claim flagged with its quote | 37 / 39 = 94.9% | 39 | marks_the_error_wrong | all patterns |
| Gap detection |  | 48 / 49 = 98.0% | 49 | gap_found | all patterns |
| No invented gap on correct work |  | 21 / 21 = 100.0% | 7 | mode_as_expected, no_gap, nothing_missing | correct_work |
| No label without evidence |  | 26 / 28 = 92.9% | 7 | mode_as_expected, no_error_stated, no_gap, no_step_wrong | no_reasoning |
| Misconception detection | concept named where expected | 13 / 14 = 92.9% | 14 | gap_is_concept | all patterns |
| Misconception detection | concept not named where the gap is not conceptual | 21 / 28 = 75.0% | 28 | gap_not_concept | all patterns |
| Answer leakage |  | 20 / 20 = 100.0% | 20 | no_answer_leak | all patterns |
| Teaching-method adherence | teaching turns with an approved draft | 36 / 53 = 67.9% | 53 | reply_approved | all patterns |
| Teaching-method adherence | drafts rejected for method drift or off-target | counts: {'off_target': 6, 'method_drift': 28} | | | |
| Repair-state detection |  | 7 / 7 = 100.0% | 7 | repair_state | repair_followup |
| Verification | approved replies free of the case's answer strings | 10 / 10 = 100.0% | 10 | no_answer_leak on replies the verifier approved | cases with answer strings |
| Verification | verifier rejection reasons across all drafts | counts: {'off_target': 6, 'method_drift': 28, 'answer_leak': 15} | | | |

## By check

| Check | Meaning | Passed / total | Cases |
| ----- | ------- | -------------: | ----: |
| credits_valid_work | a step marked correct quotes the valid work (credit_quote) | 28 / 33 = 84.8% | 33 |
| marks_the_error_wrong | a step marked wrong quotes the false or slipped claim (error_quote) | 37 / 39 = 94.9% | 39 |
| no_step_wrong | no step is marked wrong | 21 / 28 = 75.0% | 28 |
| error_stated | an error analysis is stated | 33 / 35 = 94.3% | 35 |
| no_error_stated | no error analysis is stated | 14 / 21 = 66.7% | 21 |
| gap_found | a main gap is named | 48 / 49 = 98.0% | 49 |
| no_gap | no main gap is named | 13 / 14 = 92.9% | 14 |
| gap_is_concept | the main gap is concept | 13 / 14 = 92.9% | 14 |
| gap_not_concept | a main gap is named and it is not concept | 21 / 28 = 75.0% | 28 |
| something_missing | some step is marked missing | 7 / 7 = 100.0% | 7 |
| nothing_missing | no step is marked missing | 7 / 7 = 100.0% | 7 |
| mode_as_expected | the turn's mode is one of the allowed modes | 68 / 70 = 97.1% | 70 |
| repair_state | the code repair check gives the expected result | 7 / 7 = 100.0% | 7 |
| no_answer_leak | the reply contains none of the case's answer strings | 20 / 20 = 100.0% | 20 |
| reply_approved | the verifier approved a teaching draft (no safe fallback reply) | 36 / 53 = 67.9% | 53 |

## Failure categories

| Failure category | Cases |
| ---------------- | ----: |
| Diagnosis | 14 |
| Teaching method | 7 |
| Structured output (teaching step) | 5 |
| Step segmentation | 1 |
| Evidence grounding | 1 |

Diagnosis failure types (a case can have several):

| Type | Cases |
| ---- | ----: |
| false positive error | 7 |
| false misconception | 6 |
| failure to credit valid work | 4 |
| missed error | 2 |
| missed misconception | 1 |
| invented gap | 1 |

## Case results

| Case | Domain | Pattern | Traps | Result | Failure category | Failed checks | Latency (s) |
| ---- | ------ | ------- | ----- | ------ | ---------------- | ------------- | ----------: |
| math_early_stop_phone_plan | Mathematics | incomplete_early_stop | J | PASS | - | - | 32.7 |
| math_implicit_only_solution | Mathematics | incomplete_implicit_step | - | FAIL | Diagnosis | no_step_wrong, no_error_stated, gap_not_concept | 15.7 |
| math_conceptual_square_of_sum | Mathematics | incorrect_conceptual | E | PASS | - | - | 10.1 |
| math_local_error_linear | Mathematics | incorrect_local_error | BI | FAIL | Diagnosis | marks_the_error_wrong, error_stated, reply_approved | 13.4 |
| math_right_answer_cancel_sixes | Mathematics | correct_answer_wrong_reasoning | A | PASS | - | - | 8.7 |
| math_right_reasoning_wrong_price | Mathematics | correct_reasoning_wrong_answer | C | FAIL | Diagnosis | marks_the_error_wrong, error_stated, gap_found, gap_not_concept, mode_as_expected | 34.2 |
| math_correct_trial_pairs | Mathematics | correct_work | - | PASS | - | - | 4.5 |
| math_bare_percent | Mathematics | no_reasoning | D | PASS | - | - | 7.9 |
| math_misconception_multiplying | Mathematics | misconception | - | FAIL | Structured output (teaching step) | reply_approved | 15.8 |
| math_repair_genuine_linear | Mathematics | repair_followup (genuine) | - | PASS | - | - | 3.3 |
| physics_early_stop_units | Physics | incomplete_early_stop | J | FAIL | Structured output (teaching step) | reply_approved | 12.6 |
| physics_implicit_same_fall | Physics | incomplete_implicit_step | - | FAIL | Diagnosis | credits_valid_work, no_step_wrong, no_error_stated, gap_not_concept, reply_approved | 7.7 |
| physics_conceptual_forward_force | Physics | incorrect_conceptual | E | PASS | - | - | 6.8 |
| physics_local_error_force | Physics | incorrect_local_error | BI | FAIL | Teaching method | reply_approved | 14.8 |
| physics_right_answer_mass_grows | Physics | correct_answer_wrong_reasoning | A | PASS | - | - | 26.5 |
| physics_right_reasoning_sign_slip | Physics | correct_reasoning_wrong_answer | C | FAIL | Teaching method | reply_approved | 15.7 |
| physics_correct_average_speed_route | Physics | correct_work | - | PASS | - | - | 16.8 |
| physics_bare_weight | Physics | no_reasoning | D | PASS | - | - | 8.1 |
| physics_misconception_third_law | Physics | misconception | - | PASS | - | - | 7.7 |
| physics_repair_partial_direction | Physics | repair_followup (partial) | G | FAIL | Teaching method | reply_approved | 30.2 |
| biology_early_stop_blood_sugar | Biology | incomplete_early_stop | J | PASS | - | - | 17.4 |
| biology_implicit_deforestation | Biology | incomplete_implicit_step | - | FAIL | Diagnosis | no_step_wrong, no_error_stated | 21.7 |
| biology_conceptual_mother_genes | Biology | incorrect_conceptual | E | PASS | - | - | 35.4 |
| biology_local_error_punnett | Biology | incorrect_local_error | B | FAIL | Step segmentation | credits_valid_work | 17.5 |
| biology_right_answer_whale_size | Biology | correct_answer_wrong_reasoning | A | PASS | - | - | 27.4 |
| biology_right_reasoning_meiosis_slip | Biology | correct_reasoning_wrong_answer | C | FAIL | Structured output (teaching step) | reply_approved | 26.5 |
| biology_correct_oxygen_muscles | Biology | correct_work | - | PASS | - | - | 29.6 |
| biology_bare_chloroplast | Biology | no_reasoning | D | PASS | - | - | 19.9 |
| biology_misconception_acquired_traits | Biology | misconception | - | PASS | - | - | 36.0 |
| biology_repair_false_pulmonary | Biology | repair_followup (false) | H | PASS | - | - | 34.1 |
| history_early_stop_black_death | History | incomplete_early_stop | J | PASS | - | - | 18.6 |
| history_implicit_hastings | History | incomplete_implicit_step | - | FAIL | Diagnosis | credits_valid_work, no_step_wrong, no_error_stated | 14.5 |
| history_conceptual_cold_war | History | incorrect_conceptual | - | PASS | - | - | 31.1 |
| history_local_error_interwar | History | incorrect_local_error | B | FAIL | Structured output (teaching step) | reply_approved | 63.5 |
| history_right_answer_africa_first | History | correct_answer_wrong_reasoning | A | PASS | - | - | 9.2 |
| history_right_reasoning_berlin_wall | History | correct_reasoning_wrong_answer | C | FAIL | Diagnosis | gap_not_concept, reply_approved | 11.6 |
| history_correct_shakespeare_light | History | correct_work | F | PASS | - | - | 23.9 |
| history_bare_ww2_end | History | no_reasoning | D | PASS | - | - | 25.1 |
| history_misconception_correlation | History | misconception | - | PASS | - | - | 11.5 |
| history_repair_genuine_columbus | History | repair_followup (genuine) | - | PASS | - | - | 29.1 |
| programming_early_stop_trace | Programming | incomplete_early_stop | J | PASS | - | - | 29.0 |
| programming_implicit_binary_search | Programming | incomplete_implicit_step | - | FAIL | Diagnosis | no_step_wrong, no_error_stated, gap_not_concept | 27.8 |
| programming_conceptual_aliasing | Programming | incorrect_conceptual | E | PASS | - | - | 10.8 |
| programming_local_error_squares | Programming | incorrect_local_error | BI | FAIL | Teaching method | reply_approved | 26.2 |
| programming_right_answer_floor_division | Programming | correct_answer_wrong_reasoning | A | PASS | - | - | 21.2 |
| programming_right_reasoning_index_sum | Programming | correct_reasoning_wrong_answer | C | FAIL | Teaching method | reply_approved | 30.3 |
| programming_correct_empty_list | Programming | correct_work | - | PASS | - | - | 3.9 |
| programming_bare_power | Programming | no_reasoning | D | PASS | - | - | 20.1 |
| programming_misconception_range_end | Programming | misconception | - | FAIL | Diagnosis | gap_is_concept | 31.4 |
| programming_repair_partial_indexing | Programming | repair_followup (partial) | G | FAIL | Evidence grounding | credits_valid_work | 13.9 |
| chemistry_early_stop_water_mass | Chemistry | incomplete_early_stop | J | PASS | - | - | 35.3 |
| chemistry_implicit_ionic_melting | Chemistry | incomplete_implicit_step | - | FAIL | Diagnosis | no_step_wrong, no_error_stated | 21.8 |
| chemistry_conceptual_candle_wax | Chemistry | incorrect_conceptual | - | PASS | - | - | 10.7 |
| chemistry_local_error_molar_mass | Chemistry | incorrect_local_error | BI | FAIL | Teaching method | reply_approved | 36.0 |
| chemistry_right_answer_liquids | Chemistry | correct_answer_wrong_reasoning | A | PASS | - | - | 6.3 |
| chemistry_right_reasoning_balance_slip | Chemistry | correct_reasoning_wrong_answer | C | FAIL | Diagnosis | gap_not_concept, reply_approved | 12.0 |
| chemistry_correct_moles_unsure | Chemistry | correct_work | F | PASS | - | - | 32.7 |
| chemistry_bare_ph | Chemistry | no_reasoning | D | PASS | - | - | 26.9 |
| chemistry_misconception_burning_mass | Chemistry | misconception | - | PASS | - | - | 29.3 |
| chemistry_repair_false_dissolving | Chemistry | repair_followup (false) | H | PASS | - | - | 7.6 |
| logic_early_stop_squares_chain | Logic / critical reasoning | incomplete_early_stop | J | FAIL | Structured output (teaching step) | reply_approved | 35.1 |
| logic_implicit_hidden_premise | Logic / critical reasoning | incomplete_implicit_step | - | FAIL | Diagnosis | credits_valid_work, no_step_wrong, no_error_stated | 14.5 |
| logic_conceptual_undistributed_middle | Logic / critical reasoning | incorrect_conceptual | - | PASS | - | - | 17.8 |
| logic_local_error_truth_value | Logic / critical reasoning | incorrect_local_error | B | FAIL | Diagnosis | gap_not_concept, reply_approved | 36.1 |
| logic_right_answer_cold_feathers | Logic / critical reasoning | correct_answer_wrong_reasoning | A | PASS | - | - | 27.7 |
| logic_right_reasoning_truth_table_rows | Logic / critical reasoning | correct_reasoning_wrong_answer | C | FAIL | Teaching method | reply_approved | 25.9 |
| logic_correct_prime_counterexample | Logic / critical reasoning | correct_work | F | PASS | - | - | 27.6 |
| logic_bare_modus_ponens | Logic / critical reasoning | no_reasoning | D | FAIL | Diagnosis | no_gap, mode_as_expected | 12.4 |
| logic_misconception_converse | Logic / critical reasoning | misconception | - | PASS | - | - | 13.3 |
| logic_repair_genuine_four_legs | Logic / critical reasoning | repair_followup (genuine) | - | PASS | - | - | 3.3 |

## Failures in detail

- **math_implicit_only_solution** (Diagnosis; false misconception, false positive error): failed checks: no_step_wrong, no_error_stated, gap_not_concept
- **math_local_error_linear** (Diagnosis; missed error): failed checks: marks_the_error_wrong, error_stated, reply_approved; verifier rejections: {'off_target': 2, 'method_drift': 1}; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **math_right_reasoning_wrong_price** (Diagnosis; missed error): failed checks: marks_the_error_wrong, error_stated, gap_found, gap_not_concept, mode_as_expected; mode was acknowledge, allowed ['teach']
- **math_misconception_multiplying** (Structured output (teaching step)): failed checks: reply_approved; verifier rejections: {}; draft failures: ['teaching: invalid_output: Exceeded maximum output retries (1)']
- **physics_early_stop_units** (Structured output (teaching step)): failed checks: reply_approved; verifier rejections: {'method_drift': 1}; draft failures: ['teaching: invalid_output: Exceeded maximum output retries (1)']; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **physics_implicit_same_fall** (Diagnosis; failure to credit valid work, false misconception, false positive error): failed checks: credits_valid_work, no_step_wrong, no_error_stated, gap_not_concept, reply_approved; the valid work sits inside a wrong step quoting more text; verifier rejections: {}; draft failures: ['verifier: invalid_output: Exceeded maximum output retries (1)']; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **physics_local_error_force** (Teaching method): failed checks: reply_approved; verifier rejections: {'method_drift': 3}
- **physics_right_reasoning_sign_slip** (Teaching method): failed checks: reply_approved; verifier rejections: {'method_drift': 1, 'off_target': 1, 'answer_leak': 1}; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **physics_repair_partial_direction** (Teaching method): failed checks: reply_approved; verifier rejections: {'method_drift': 2, 'answer_leak': 1}; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **biology_implicit_deforestation** (Diagnosis; false positive error): failed checks: no_step_wrong, no_error_stated
- **biology_local_error_punnett** (Step segmentation; failure to credit valid work): failed checks: credits_valid_work; the valid work sits inside a wrong step quoting more text
- **biology_right_reasoning_meiosis_slip** (Structured output (teaching step)): failed checks: reply_approved; verifier rejections: {}; draft failures: ['teaching: invalid_output: Exceeded maximum output retries (1)']
- **history_implicit_hastings** (Diagnosis; failure to credit valid work, false positive error): failed checks: credits_valid_work, no_step_wrong, no_error_stated
- **history_local_error_interwar** (Structured output (teaching step)): failed checks: reply_approved; verifier rejections: {'method_drift': 1, 'off_target': 1}; draft failures: ['teaching: invalid_output: Exceeded maximum output retries (1)']; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **history_right_reasoning_berlin_wall** (Diagnosis; false misconception): failed checks: gap_not_concept, reply_approved; verifier rejections: {'answer_leak': 3}; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **programming_implicit_binary_search** (Diagnosis; false misconception, false positive error): failed checks: no_step_wrong, no_error_stated, gap_not_concept
- **programming_local_error_squares** (Teaching method): failed checks: reply_approved; verifier rejections: {'method_drift': 2, 'off_target': 1}
- **programming_right_reasoning_index_sum** (Teaching method): failed checks: reply_approved; verifier rejections: {'method_drift': 2, 'off_target': 1}
- **programming_misconception_range_end** (Diagnosis; missed misconception): failed checks: gap_is_concept
- **programming_repair_partial_indexing** (Evidence grounding): failed checks: credits_valid_work; a correct step exists but none quotes the valid work
- **chemistry_implicit_ionic_melting** (Diagnosis; false positive error): failed checks: no_step_wrong, no_error_stated
- **chemistry_local_error_molar_mass** (Teaching method): failed checks: reply_approved; verifier rejections: {'method_drift': 3}
- **chemistry_right_reasoning_balance_slip** (Diagnosis; false misconception): failed checks: gap_not_concept, reply_approved; verifier rejections: {'answer_leak': 3}; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **logic_early_stop_squares_chain** (Structured output (teaching step)): failed checks: reply_approved; verifier rejections: {}; draft failures: ['teaching: invalid_output: Exceeded maximum output retries (1)']
- **logic_implicit_hidden_premise** (Diagnosis; failure to credit valid work, false positive error): failed checks: credits_valid_work, no_step_wrong, no_error_stated; the valid work sits inside a wrong step quoting more text; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **logic_local_error_truth_value** (Diagnosis; false misconception): failed checks: gap_not_concept, reply_approved; verifier rejections: {'answer_leak': 3}; several categories apply; primary chosen by the fixed order Infrastructure/API > Timeout > Structured output > Diagnosis > Step segmentation > Evidence grounding > Answer leakage > Structured output (teaching step) > Timeout (teaching step) > Teaching method > Verification > Other
- **logic_right_reasoning_truth_table_rows** (Teaching method): failed checks: reply_approved; verifier rejections: {'method_drift': 3}
- **logic_bare_modus_ponens** (Diagnosis; invented gap): failed checks: no_gap, mode_as_expected; mode was teach, allowed ['acknowledge', 'probe']

## Comparison with v1 (separate benchmarks, not combined)

Separate benchmarks: not combined into one score. v1 is 21 cases, 3 patterns, one run each. The v2 numbers here use v1's exact criteria on the three v2 patterns that correspond to v1's.

v1 overall: 20 / 21 = 95.2% (21 cases).

| Pattern | v1 result | v2 result (v1's criteria) | v2 cases |
| ------- | --------: | ------------------------: | -------: |
| incomplete_early_stop | 6 / 7 = 85.7% | 7 / 7 = 100.0% | 7 |
| incorrect_conceptual | 7 / 7 = 100.0% | 7 / 7 = 100.0% | 7 |
| correct_answer_wrong_reasoning | 7 / 7 = 100.0% | 7 / 7 = 100.0% | 7 |
