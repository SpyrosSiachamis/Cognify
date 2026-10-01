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
| Outcome | VERIFIED or NOT YET, evidence, independence, hints used, remaining gap | The result of the loop | F16, F17 |
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
| verified | fragile | A later NOT YET on the same concept |

Other moves between strong, weak and fragile follow the diagnosis evidence. Details belong in `ARCHITECTURE.md`.

## Reads the app needs

- Best method per gap type for a learner (most independent successes, with the counts).
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
