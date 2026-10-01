# ARCHITECTURE

How Cognify works inside the backend. Read this before writing any backend code.
Scope lives in `SPEC.md`. Rules live in `CLAUDE.md`. Field-level detail lives in `API_CONTRACT.md`.

## The idea in one paragraph

The student only ever talks to **one agent**. That agent diagnoses the student, gets a teaching method from a **rule-based policy tool**, and writes either a teaching reply or a follow-up problem. A separate **verification LLM** checks everything before the student sees it. **Plain code** owns the flow, the history and the final VERIFIED decision. The model never grades its own teaching.

## The loop

```
Student
  |  attempt (text)
  v
+--------------------------------------------+        +---------+
| TUTOR AGENT (reasoning + tutor in one)     |<------>| HISTORY |
|  1. split the answer into steps, diagnose  |  tool  +---------+
|  2. call choose_strategy (rule-based)      |
|  3. write the reply OR the follow-up       |
+--------------------+-----------------------+
                     | draft
                     v
+--------------------------------------------+
| VERIFICATION LLM                           |
|  reply check / follow-up check             |
+--------------------+-----------------------+
        approved     |      rejected
            |        |         |
            v        |         +--> regenerate with the reason (max 2), then safe fallback
         Student     |
```

At the end of the loop the same verification LLM also judges the student's follow-up attempt (see "Verifier modes").

## Who does what

| Piece | Kind | Owns |
|---|---|---|
| Session state machine | Code | Which phase we are in, hint counts, caps, what happens next |
| Tutor agent | AI | Step splitting, diagnosis with evidence, teaching reply, probe, follow-up problem |
| `choose_strategy` tool | Code | Picking the teaching method from history, including experiments |
| Verification LLM | AI | Judging replies, follow-up problems and the student's follow-up attempt |
| Novelty check | Code | Rejecting a follow-up the student has already seen (normalised text hash) |
| VERIFIED decision | Code | Combines the verifier's judgement, hint count and "was the problem fresh" |
| History | Code + database | Concept states, strategy records, past outcomes. Only the backend reads and writes it |
| Level 1 answer | AI, single call | Direct solution. No verifier, no history, no writes |

## Session phases (the state machine)

```
START -> ASK_FIRST_THOUGHT -> TEACH <-> TEACH ... -> STRESS_TEST -> VERDICT
                                  ^                                   |
                                  +------------- NOT_YET (max 2) -----+
                                                                      |
                                                              VERIFIED -> END
EXIT can happen from any phase.
```

- **ASK_FIRST_THOUGHT:** the app asks what the student would try first. No help is given.
- **TEACH:** diagnosis, method, one small teaching move. The student replies; repeat. A probe is a TEACH turn whose job is to separate two possible causes.
- **STRESS_TEST:** a fresh follow-up problem with no hints.
- **VERDICT:** the verifier judges the follow-up attempt, then code decides VERIFIED or NOT YET.
- **Skip rule:** if the first thought is already correct and independent, go straight to STRESS_TEST. Being right on the original problem is not VERIFIED.
- **Move-on rule:** the agent reports whether the gap looks repaired, with evidence. Code moves to STRESS_TEST when it does, or after 4 TEACH turns regardless.
- **NOT YET:** the agent gets the new evidence, re-diagnoses, and teaches again. Maximum 2 times, then end gracefully (say what was learned, offer to exit).

## The `choose_strategy` tool (Idea A lives here)

The agent must call this tool after diagnosing. It is plain code, not AI.

- **Input:** the gap type, the concept, the student.
- **Output:** the method, the decision mode (`best_known`, `experiment` or `cold_start`), a one-line reason, and the evidence behind it (for example "worked 7 of 9 times for you").
- **The app records this result.** What the screen shows and what history credits comes from the tool result, never from the model's own wording.

Rules, in order:

1. **No history for this gap type:** use the default method for that gap (`cold_start`).
2. **Choose the best known method:** highest score for this student and gap type, where score = (independent successes + 1) / (uses + 2). This counts every method as if it had already failed once and succeeded once, so a lucky 1 of 1 (0.67) does not beat a solid 7 of 9 (0.73). Ties go to the method with more uses. The screen still shows the raw counts.
3. **Experiment check.** Replace the best method with a challenger when all of these hold:
   - roughly 1 in 5 Master sessions (a demo flag can force it),
   - the previous session on this gap was not already an experiment,
   - we are in TEACH, never in STRESS_TEST or VERDICT.
4. **Pick the challenger:** an untried method for this gap first, then the least-tested, then one whose last success is older than about 30 days.
5. **Fail-safe:** if an experiment's teaching turn gets NOT YET, the retry returns to the best known method in the same session.

The experiment outcome counts as evidence like any other. A failed experiment is still useful.

**Reward after a verdict** (used to update the strategy record): independent success on the fresh problem, plus fewer hints than last time on this gap, minus hints used. Keep the formula simple enough to explain in one sentence.

## Verifier modes

One model role, three jobs. Each job has its own prompt and its own inputs (see `PROMPTS.md`).

| Mode | When | Checks | Result |
|---|---|---|---|
| Reply check | Every Master reply | Contains the answer? Gives a heavy hint? Uses a different method than the one chosen? Tone shaming? | approved, or rejected with a reason |
| Follow-up check | Every follow-up problem | Same underlying principle? Different surface? Solvable? Does the statement give the answer away? | approved, or rejected with a reason |
| Student check | The student's follow-up attempt | Is the reasoning correct? Is it the student's own work (given the hints used and the teaching so far)? | judgement used by code to decide VERIFIED |

The method-drift check matters for Idea A: if a reply uses a different method than the tool chose, the wrong method would get credit in history.

Before the LLM check, run a cheap code check on every Master reply: the final answer string must not appear in it. It is fast and catches the worst leak for free.

## Caps and fallbacks

| Situation | What happens |
|---|---|
| Reply or follow-up rejected | Regenerate with the reason. After 2 rejections, send a safe generic question ("What would you try next?") or, for a follow-up, a curated fallback problem for the concept. |
| Model reply not valid | Retry once, then fall back. A bad reply never crashes a screen. |
| Model call too slow | Per-call timeout, then fall back. |
| Verdict is NOT YET twice | End gracefully. Record the outcome as not verified. |
| Demo mode on | Backend returns the saved Maria story. The frontend cannot tell the difference. |
| Student sends nothing useful | Ask one short constrained question. Never explain instead. |

## What each side can see

| Thing | Agent | Verifier | Frontend |
|---|---|---|---|
| Problem and student's text | yes | yes | yes |
| Worked solution (hidden) | yes | yes | **never** |
| Hidden rubric for a follow-up | yes (writes it) | yes | **never** |
| History | only via `choose_strategy` | no | only the two views |
| Chosen method | yes | yes | yes, with the reason |
| Verifier's notes | no | yes | only a short summary |

## Latency

A normal turn is one agent run (with one tool call) plus one reply check. A verdict turn adds the student check. Because replies are checked before they are sent, **tutor text does not stream**. Show a "thinking" state, and optionally a stage line such as "Reading your steps", "Choosing a method", "Checking the reply".

Optional speedup: start the next phase's work while the verifier runs only if it is simple. Do not add complexity here before the full loop works.

## Backend layout

```
backend/app/services/
  ai_gateway       all model calls, timeouts, retries, validation
  tutor            state machine + the agent run
  strategy_choice  the choose_strategy tool and the policy rules
  novelty          repeat detection for follow-up problems
  verification     the three verifier modes
  history          reads and writes concept states, strategy records, outcomes
backend/prompts/   tutor.txt, verifier_reply.txt, verifier_followup.txt,
                   verifier_student.txt, level1.txt
```

## Decisions already made

- No separate public diagnose or verify endpoints. The frontend only talks to the tutor.
- Method choice is code, not the model.
- Confidence is a label (low, medium, high), never a made-up percentage.
- One demo user per learner (Maria, Nikos). No login.
- Only the backend touches the database. Only Master verdicts write to the learner models.
