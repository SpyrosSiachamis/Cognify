# Demo

Uses the honest wording from `CLAUDE.md` rule 12: "observed strategy effectiveness", "evidence-backed diagnosis". Seeded data is always shown as "seeded demo history". Examples and values: `API_CONTRACT.md`.

## Maria script (about 4 minutes)

| # | Who clicks | What happens | Say |
|---|---|---|---|
| 1 | Presenter | Problem Inbox: "Try an example" (ball thrown up at 20 m/s), Continue | "Any subject works. The ball is just our example." |
| 2 | Presenter | Depth Selector: pick Master | "Answer gives a result. Master teaches." |
| 3 | Presenter | Type Maria's first thought: found the time, cannot get the height | "It asks before it helps." |
| 4 | Presenter | Gap Reveal: `recognition`, quote, confidence `medium` | "Evidence-backed diagnosis: it quotes her words." |
| 5 | Presenter | Method: visual decomposition, "Worked 7 of 9 times for you" (seeded demo history) | "Observed strategy effectiveness, from her history." |
| 6 | Presenter | Answer the sketch prompt | "One small move. No answer." |
| 7 | Presenter | Stress test: the balcony stone, no hints | "Support removed." |
| 8 | Presenter | Solve it alone; Verdict: VERIFIED | "Code decides VERIFIED, from independence and hints." |
| 9 | Presenter | Signature animation, then My Learning | "Fragile to verified, 7 of 9 becomes 8 of 10." |

To show an experiment: start the session with the demo flag `force_experiment`. The screen says "Trying something different this time." Experiments never happen in the stress test.

## Nikos comparison (about 1 minute)

Same ball problem. Nikos picks the right equation but gets the sign wrong, so the gap is `procedure`, the method is a worked example, and his follow-up is the downward throw. Different diagnosis, method and follow-up (SPEC section 5, F22).

## 90-second pitch

Cognify is a problem-solving tutor that learns how a student thinks. Most tutors hand over the answer. Cognify's Master mode asks first, splits the student's answer into steps, and finds the exact step where it breaks, quoting the student's words. It teaches with the method that has worked for that student, and now and then tries a different one and says so. Then it takes the help away and sets a fresh problem built from the student's own gap. Only when they solve it alone does Cognify say VERIFIED. Both sides learn: the concept moves from fragile to verified, and the observed strategy effectiveness updates. Same problem, two students, two different paths.

## Judge Q&A

| Question | Answer |
|---|---|
| How do you stop it giving the answer away? | A verification LLM checks every reply and follow-up for the answer, a heavy hint and method drift before the student sees it. A rejected reply is regenerated with the reason, up to 2 times, then replaced by a safe fallback. Code also checks that the final answer string is not in the reply. |
| Who decides VERIFIED? | Code, not the model. It uses the verifier's judgement, the hint count and whether the problem was fresh. |
| Is the exploration real? | Yes. About one Master session in five tries a different method, preferring one never tried for that gap. It is labelled on screen and recorded. Rules in SPEC section 5. |
| What is Dream-RSI-inspired about it? | It keeps testing whether its own best guess is still the best, and records the result. We say "inspired by", not more. |
| Why does Level 1 exist? | Students sometimes just want the answer. It is stateless, writes nothing and never counts as mastery evidence. |
| What if the model fails? | Replies are validated, retried once, then a safe fallback is used, so no screen crashes. The offline path plays the full story with no AI. |

## Offline switch (F27)

Set `DEMO_MODE=offline` in `.env`, then run `docker compose up -d backend` (a plain restart does not reload `.env`). The backend then plays the saved Maria and Nikos story with the same response shapes, so the frontend cannot tell. It needs no network, no AWS credentials and no model, and it works even when `TUTOR_MODEL_ID` is still set. The backend log says `tutor: OFFLINE DEMO` on start. To go back, empty `DEMO_MODE` and run the same command.

- Whatever problem is pasted, the saved ball story is what plays. It is a rehearsal, not a solver.
- A mistyped value (for example `ofline`) stops the backend at start, so the real tutor never runs by accident.
- Check it once before the demo: `python demo/play_story.py` plays the whole story and prints PASS or FAIL for every step.

## Run the backend for the live demo

The normal `docker compose up` runs the backend with `uvicorn --reload` and the source mounted, so saving any backend file restarts it and every open session and the in-memory history are lost (the student sees "This session was lost"). For the demo use the production override, which copies the code into the image and does not reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build backend
docker compose ps                       # backend shows (healthy)
python demo/play_story.py               # plays the whole story and checks every step
```

- One worker only: the in-memory history store needs exactly one process.
- To reset the seeded history between rehearsals: `docker compose -f docker-compose.yml -f docker-compose.demo.yml restart backend`.
- To go back to development, use the plain file: `docker compose up -d --build backend`.
- Do not run `docker compose config` on a shared screen: it prints the values from `.env`.

## Pre-flight checklist

- [ ] Backend started with the demo override (`docker-compose.demo.yml`), `docker compose ps` shows it healthy, and `curl localhost:8000/health` is OK
- [ ] Seeded history reloaded (the one-step reset in `DATA.md`); Maria is fragile at 7 of 9
- [ ] Full Maria story run once, end to end
- [ ] Offline switch tested (`DEMO_MODE=offline`, then `python demo/play_story.py`), then set back
- [ ] The Nikos comparison works
- [ ] Experiment demo flag tested
- [ ] Second device opens the public address (F28)
- [ ] No real keys on screen; seeded badge visible
