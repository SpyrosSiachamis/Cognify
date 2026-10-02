# Data: what the app remembers

Plain language only. There are no column or table definitions here; the schema lives in `supabase/`. Names (phases, gap types, strategies, states) are the ones in `API_CONTRACT.md`. All IDs are UUIDs.

## What is remembered, and why

| Record | What it holds | Why | Features |
|---|---|---|---|
| Learner | Who the student is: id, display name, seeded flag | Everything else hangs off a learner | F24 |
| Problem | The problem text, subject, and a fingerprint of it | Spot repeats; never give a student the same problem twice | F14 |
| Session | One Master run: learner, problem, current phase, hints used, whether it was exited | Code owns the flow, so the phase must survive between turns | F6, F16 |
| Attempt | One student message, split into steps (role, status, quote) | The evidence every diagnosis must quote | F7 |
| Diagnosis | Main gap, alternatives, confidence label, dimension ratings with evidence | Shows the Gap Reveal and explains later choices | F8, F9 |
| Strategy decision | Method, decision mode, experiment flag, reason, evidence counts at that moment | "Every experiment is recorded"; the on-screen reason | F11, F12 |
| Follow-up problem | The problem text, fingerprint, target gap, target step, perturbation, difficulty, hidden rubric | Never repeat; the verifier needs the rubric; the rubric stays on the backend | F14, F15 |
| Outcome | VERIFIED or NOT YET (with its reason: incorrect, not_own_work or hint_limit), evidence, independence, hints used, remaining gap | The result of the loop | F16, F17 |
| Reply draft | Each teaching draft of a turn: outcome (approved, verifier_rejected, teaching_failed, verifier_error, wrong_language), the verifier's reason and note, the method | Debugging why a safe fallback was sent; never shown to students | F30 |
| Session trace event | Development only (`DEBUG_TRACE`): one typed event per stage of a session (student response, model call, reasoning read, diagnosis, each draft and its check, fallback, reply sent, state transition, support removed, follow-up, fresh problem, transfer result, error, start and end), numbered in order | Reconstruct a session after the fact and compare sessions; never read by the tutor and never shown to students | F25, F30 |
| Concept state | Per learner and concept: strong, fragile, weak, untested or verified, plus evidence lines | Understanding Map | F18 |
| Strategy record | Per learner, gap type and method: uses, independent successes, experiments, last success date | Best-method choice and How You Learn | F11, F12, F19 |

## Write rules

- **Level 1 writes nothing.** It never touches the learner.
- Attempts, diagnoses, decisions and follow-up problems are saved during the session, as they happen.
- **Only a Master verdict** updates concept state and strategy records. This is done by code, in one step, so both views change together.
- **Exit records no evidence.** The session is marked exited; nothing else changes.
- Seeded rows always carry the seeded flag.

## Concept state moves

| From | To | When |
|---|---|---|
| untested | fragile | First evidence about the concept |
| fragile | verified | Only on a verified, fresh follow-up with independence |
| verified | fragile | A later NOT YET on the same concept that is evidence against it (incorrect, or not the student's own work). A hint_limit NOT YET (correct and own work, but more help than F16 allows) leaves a verified concept verified: it is about help, not regression. A failed judgement records nothing. |

Other moves between strong, weak and fragile follow the diagnosis evidence. Details belong in `ARCHITECTURE.md`.

**Hints (F16).** A hint is an approved teaching move that reached the student; it is counted on the student's next answer. A safe fallback, a probe, an acknowledgement, the blank-text question, a failed turn and a reply replaced by the fresh problem are not hints. Only a delivered move is recorded as a strategy decision, and a verdict credits the last move delivered in the current teaching cycle. The context the next answer is read against is separate: it is the last reply the student saw, probes and fallbacks included, and it adds no hint.

**Practice problem after a NOT YET.** A first NOT YET stores the fresh problem it was given on, with its own solution from the set-up step, as the session's active practice problem. The repair cycle that follows diagnoses against it; when that cycle moves on, it is cleared and a new fresh problem (never one the student has seen) is the only route to VERIFIED. The session keeps its original problem for history, the concept and learner state, and exit.

**Concept identity (known limitation).** There is no concept ontology. A concept is the `Concept` row whose name the set-up step chose; names are matched only after trimming spaces and ignoring case. The set-up step is shown the names of concepts that already have a recorded verdict and is told to reuse one exactly, but that is the model's choice: the same idea can be named differently on different runs (a new concept row), and two different ideas can share a name (one concept row). Verdicts and concept states follow the row, so a label change splits evidence and a wrong reuse merges it. The hint_limit rule above limits the damage of a wrong merge; a canonical concept identifier is outside this change.

## Reads the app needs

- Best method per gap type for a learner: the highest smoothed score, (independent successes + 1) / (uses + 2), with the raw counts kept. Ties go to the method with more uses.
- Overall counts per method (uses and independent successes summed across gap types) for the How You Learn view.
- Last success date per method (old evidence expires, SPEC section 5).
- Follow-up fingerprints this learner has already seen.
- The two views: `GET /api/learner/{student_id}` and `GET /api/strategies/{student_id}`.

## Seeded demo history

Always labelled **"seeded demo history"** (F24). Nothing synthetic is shown as real.

| | Maria `16e82ef2-adee-4671-8393-c6b50ac91672` | Nikos `00915798-79f9-4362-84d0-839a0b3df9f2` |
|---|---|---|
| Concept | Constant-acceleration kinematics | Constant-acceleration kinematics |
| History | Recognition gap in earlier sessions | Procedure gap in earlier sessions |
| Concept state | fragile | fragile |
| Strategy record | visual_decomposition 7 of 9; worked_example 4 of 7; socratic 3 of 5; analogy and counterexample untried | worked_example works best (counts set in the seed) |

Nikos' exact counts and his concept state are an assumption to confirm in the seed; the brief only says worked example works best.

## Reset for rehearsals

One command reloads the seed and deletes every non-seeded session, attempt, decision and outcome, so Maria is back at 7 of 9 and fragile. The command lives with the seed in `supabase/` and is run before every rehearsal (see the pre-flight list in `DEMO.md`).
