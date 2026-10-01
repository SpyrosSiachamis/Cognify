# Prompts

In plain words, no code. Names come from `API_CONTRACT.md`. Prompt files live in `backend/prompts/`: `tutor.txt`, `verifier_reply.txt`, `verifier_followup.txt`, `verifier_student.txt`, `level1.txt`. Every model reply is validated against its Pydantic model before use; one retry, then a safe fallback.

## Shared rules (every prompt)

- Cite the student's own words as evidence. No quote, no claim.
- Low confidence means ask one short probe, not assign a label.
- One new idea per turn.
- Never reveal the full solution in Master.
- Warm tone, never shaming.
- Reply in the student's language (English or Greek).
- The product is subject-agnostic. The ball problem is only the demo.
- Confidence is `low`, `medium` or `high`, never a number.

## Tutor agent (`tutor.txt`)

**Job:** split the student's text into steps, diagnose, call `choose_strategy`, and write either a teaching reply (or probe) or a follow-up problem.

**Inputs:** problem, student text, session phase, hints used, the hidden solution, and the retry reason if the verifier rejected the last try.

**The `choose_strategy` result must be used, never overridden.** The reply uses that method. The model may not pick another.

**Produces:** see Part B of `API_CONTRACT.md` (steps, dimensions, main gap, alternatives, confidence, gap-repaired flag, reply or follow-up).

**Step names:** `identify_quantities`, `choose_method`, `set_up`, `substitute`, `compute`, `interpret`. Each step is `correct`, `wrong` or `missing`, with a quote.

**The nine dimensions:** correctness, recognition, representation, concept, procedure, strategy choice, self-correction, hint dependency, transfer. Each is rated Strong, Fragile, Weak or Untested, with evidence. Show only the 3 to 5 most relevant.

**Ball problem worked through** (Maria: "I found the time to the top, about 2.04 s, but I do not know how to get the height from the time."):
- `identify_quantities` is correct. Quote: "initial velocity of 20 m/s".
- `choose_method` is wrong. Quote: "I do not know how to get the height from the time".
- Recognition: Weak (found the time, saw no way to the height). Procedure: Strong (time computed correctly).
- Main gap `recognition`, alternative `representation` at low confidence, overall confidence `medium`.
- Reply: one small move (sketch it, mark where the speed is 0). No equation, no answer.

**Follow-up rules:** keep the same principle; change the surface toward the weakest step; never repeat a problem this student has seen; never give the answer away. Full rules: `SPEC.md` section 5.

## Verifier (three modes)

| Mode | Inputs | Checks | Rejection reasons |
|---|---|---|---|
| Reply check (`verifier_reply.txt`) | Tutor reply, hidden solution, chosen method, hints used | States the answer? More than a small hint? Matches the chosen method? Warm tone? | `answer_leak`, `heavy_hint`, `method_drift`, `shaming_tone` |
| Follow-up check (`verifier_followup.txt`) | Follow-up problem, hidden rubric, concept invariant | Same principle? Surface changed? Does not state the answer? Solvable? (Repeats are caught earlier by the code novelty check.) | `invalid_followup`, `answer_leak` |
| Student check (`verifier_student.txt`) | Student's follow-up attempt, hidden rubric, hint count | Correct? Reasoning quality? Own work? | `not_independent` |

Code also runs a cheap check before the reply check: the final answer string must not appear in the reply. The verifier returns a short note and, for the student check, `correct`, a reasoning-quality label and `own_work`. It does **not** decide VERIFIED. Code does, using the verifier's judgement, the hint count and freshness.

## Level 1 (`level1.txt`)

Result plus short steps. Stateless, writes nothing, never counts as evidence.

## Golden test cases (ball problem)

1. **Maria, first thought:** diagnosis is `recognition`; reply is a sketch prompt; no answer, no equation.
2. **Nikos, first thought:** picks the right equation, signs wrong, negative height; main gap `procedure`.
3. **Probe case:** a vague first thought gives low confidence, so the reply is one probe, not a label.
4. **Leak:** a reply that states "20.4 m" is rejected as `answer_leak`.
5. **Drift:** a reply using a method other than the chosen one is rejected as `method_drift`.
6. **Follow-ups differ:** Maria gets the balcony stone; Nikos gets the downward throw (`SPEC.md` section 5). Neither repeats the ball problem.
7. **Lucky answer:** a correct follow-up after many hints is not VERIFIED (F16).
8. **Greek:** a Greek first thought gets a Greek reply with the same diagnosis.
