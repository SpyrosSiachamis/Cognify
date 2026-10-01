# Cross-domain evaluation

A small, hand-designed cross-domain generalization evaluation of Cognify's reasoning and diagnosis behaviour. It asks one question: can the tutor tell what a student has actually shown from what is unfinished or wrong, outside the seeded physics problem? It is **not** a measure of educational accuracy or effectiveness: 21 cases written by hand, 3 per domain, each run once on one model.

- Model: Mistral Large 3 (`mistral.mistral-large-3-675b-instruct`); one run per case, no reruns.
- Tutor code: commit a2d2554 (backend/app unchanged for this run); entry point: AgentTutor.set_up then AgentTutor.teach_with_trace (as in test_general_live.py).
- Cases and their written expectations: `backend/tests/tutor/cross_domain_cases.py`; only the problem and the student's text reach the tutor. Test: `backend/tests/tutor/test_cross_domain_live.py`.
- Full per-case data, including the actual diagnosis and the expected one: `docs/cross_domain_evaluation.json`.

Pass criteria, fixed before the run (the evidence quote is matched ignoring case and spaces):

- **incomplete**: a correct step quotes the shown work; no step wrong; no error stated; something still missing; a gap found that is not concept; the turn teaches.
- **incorrect**: a step marked wrong quotes the false claim; an error stated; a gap found; the turn teaches.
- **correct_answer_wrong_reasoning**: same as incorrect: the false reasoning is marked wrong although the answer is right.

## Summary

Overall: **20 / 21 = 95.2%**.

| Domain | Passed | Total | Pass rate |
| ------ | -----: | ----: | --------: |
| Mathematics | 3 | 3 | 100.0% |
| Physics | 3 | 3 | 100.0% |
| Biology | 3 | 3 | 100.0% |
| History | 3 | 3 | 100.0% |
| Programming | 3 | 3 | 100.0% |
| Chemistry | 3 | 3 | 100.0% |
| Logic / critical reasoning | 2 | 3 | 66.7% |

| Pattern | Passed | Total | Pass rate |
| ------- | -----: | ----: | --------: |
| incomplete | 6 | 7 | 85.7% |
| incorrect | 7 | 7 | 100.0% |
| correct_answer_wrong_reasoning | 7 | 7 | 100.0% |

## Case results

| Case | Domain | Pattern | Result | Failure category |
| ---- | ------ | ------- | ------ | ---------------- |
| math_incomplete_factoring | Mathematics | incomplete | PASS | - |
| math_incorrect_percent | Mathematics | incorrect | PASS | - |
| math_right_answer_prime_rule | Mathematics | correct_answer_wrong_reasoning | PASS | - |
| physics_incomplete_energy | Physics | incomplete | PASS | - |
| physics_incorrect_falling | Physics | incorrect | PASS | - |
| physics_right_answer_no_weight | Physics | correct_answer_wrong_reasoning | PASS | - |
| biology_incomplete_breathing | Biology | incomplete | PASS | - |
| biology_incorrect_plant_mass | Biology | incorrect | PASS | - |
| biology_right_answer_eye_colour | Biology | correct_answer_wrong_reasoning | PASS | - |
| history_incomplete_printing | History | incomplete | PASS | - |
| history_incorrect_telegraph | History | incorrect | PASS | - |
| history_right_answer_older_country | History | correct_answer_wrong_reasoning | PASS | - |
| programming_incomplete_average | Programming | incomplete | PASS | - |
| programming_incorrect_range | Programming | incorrect | PASS | - |
| programming_right_answer_modulo | Programming | correct_answer_wrong_reasoning | PASS | - |
| chemistry_incomplete_moles | Chemistry | incomplete | PASS | - |
| chemistry_incorrect_dissolving | Chemistry | incorrect | PASS | - |
| chemistry_right_answer_ice | Chemistry | correct_answer_wrong_reasoning | PASS | - |
| logic_incomplete_syllogism | Logic / critical reasoning | incomplete | FAIL | Diagnosis |
| logic_incorrect_converse | Logic / critical reasoning | incorrect | PASS | - |
| logic_right_answer_even | Logic / critical reasoning | correct_answer_wrong_reasoning | PASS | - |

## Observations

- **The one failure (logic_incomplete_syllogism)** is the same pattern the step rules are meant to prevent: the student's valid inference ("all whales are warm-blooded") and their "I'm not sure how the third premise fits in" were quoted together as one step and labelled `missing`, so no step credits the correct work. The diagnosis's own dimensions ("correctly combines the first two premises") and the reply ("You've rightly seen that all whales are warm-blooded") do credit it; the step labels do not. One case, one run: it shows the pattern can still occur, not how often.
- **Incomplete work was not called wrong** in any of the 7 incomplete cases: no step was marked wrong and no error was stated in any of them, and the gap was never `concept` (recognition 5, representation 1, procedure 1).
- **False claims were found in all 14 incorrect and correct-answer-wrong-reasoning cases**, each with a stated error and a step quoting the false claim, including the 7 where the final answer was right.
- **`concept` is the default label for a false claim**: 13 of those 14 got main_gap `concept`, including a false date (history) and an invalid inference (logic), where another label could fit. The pass criteria do not test the gap type for these patterns, so this is recorded, not counted.
- **The fixed step roles are reused outside mathematics**: the tutor has six roles (identify_quantities, choose_method, set_up, substitute, compute, interpret), and non-mathematical evidence was placed in them loosely (for example a historical date claim under choose_method, a biology claim under identify_quantities). The checks do not depend on the role, so this did not affect the results.
- **Teaching replies**: in 2 of 21 turns (physics_right_answer_no_weight, programming_incorrect_range) the verifier approved no draft and the safe fallback reply was sent. This is outside the pass criteria, which test the diagnosis and that the turn teaches.
- **Latency** (set-up plus the full teaching turn, cases run one at a time): median 17.5 s, range 6.5 to 42.0 s.
- No infrastructure, timeout or structured-output failures occurred in this run.
