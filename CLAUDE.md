# Cognify (FuturEd AI 2026)

A problem-solving tutor that learns how a student thinks and keeps testing whether its best teaching method is still the best. The student pastes a problem and picks a depth. We build only **Level 1 (Answer)** and **Level 5 (Master)**; the depth selector shows just those two cards. The product is for general subjects, not one subject. In **Master mode** the app splits their answer into steps, finds the gap, teaches with the method that has worked for them (sometimes an experiment), gives a personal follow-up, and only says VERIFIED when they solve it without help.

`SPEC.md` is the single source of truth for scope. Read it before building anything.

## Rules

1. **No feature without an ID in SPEC.md.** New ideas go to the Parked list with a one-line reason, not into code.
2. **Demo reliability beats features.** The Maria story (ball thrown up at 20 m/s) must run end to end after every change. Keep the offline path (F27) working.
3. **Never use an AI answer without checking it.** Validate every model reply with Pydantic, retry once, then fall back safely. Calls have timeouts. A bad reply must never crash a screen (F25).
4. **One AI doorway.** All model calls go through `backend/app/services/ai_gateway`. Swapping the model touches one file (F26).
5. **No provider keys or provider calls in the frontend.** The frontend only talks to our backend.
6. **Master never reveals the full answer.** One small teaching move per turn, never more than one new idea (F6, F13).
7. **Every diagnosis quotes student evidence.** Low confidence means ask a probe, not assign a label. No made-up percentages.
8. **Every experiment is labelled on screen and recorded.** Experiments never happen during verification (F12).
9. **Judge independence separately from correctness.** A lucky correct answer after many hints is NOT YET (F16).
10. **Level 1 never counts as mastery evidence** and never touches the learner model.
11. **Seeded data is always labelled** "seeded demo history" (F24). Nothing synthetic is shown as real.
12. **Honest wording:** "observed strategy effectiveness", "evidence-backed diagnosis". Never "learning styles" or "visual learner".
13. **Run tests after each change.**
14. Tone toward students is warm and never shaming. Colours: green is used only for VERIFIED (buttons are not green; use navy/gold), amber for in progress, warm red for gaps.

## Stack (as built)

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind in `frontend/`; Next's file routing handles navigation. Planned: shadcn/ui, Zustand (Master loop state machine), TanStack Query, KaTeX, Recharts, Framer Motion.
- **Backend:** Python 3.13, FastAPI + Uvicorn in `backend/`, Pydantic v2 for validation.
- **AI:** Pydantic AI on AWS Bedrock (region from `AWS_REGION`, EU). Anthropic models in EU need an `eu.`-prefixed inference profile ID.
- **Database:** Supabase Postgres (`supabase/postgres` image locally).
- **Tests:** pytest (backend), Vitest + React Testing Library (frontend), Playwright optional.

## Running locally

```bash
docker compose up --build        # db :5432, backend :8000, frontend :3000
curl localhost:8000/health       # {"status":"ok"}
```

- Config lives in `.env` (gitignored); copy `.env.example`. Bedrock auth is `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + `AWS_REGION`. Never commit or print real keys.
- After editing `.env`, run `docker compose up -d <service>`; a plain restart does not reload it.
- Source is bind-mounted, so backend (uvicorn `--reload`) and frontend (`next dev`) hot reload.
- This machine uses Colima. If published ports are unreachable from the host, run `colima restart`.

## Layout

```
frontend/            Next.js app
backend/app/         FastAPI entry point, routes, Pydantic models
backend/app/services/  ai_gateway, reasoning, diagnosis, strategy_choice,
                       followup, novelty, verification
backend/prompts/     one text prompt per service
backend/tests/
supabase/            schema and seeded demo history
demo/                Maria story, offline fallback, pitch notes
docs/                LEVELS, REASONING, TEACHING, FOLLOWUPS, SCREENS, PROMPTS, DATA, DEMO
```

Not all of these exist yet; create them as the milestones need them.

## Build order

Follow the milestones in SPEC.md section 6 (M0 health, M1 hardcoded slice, M2 real diagnosis, M3 adaptive teaching, M4 follow-up and verifier, M5 memory, M6 two-learner views, M7 reliability, M8 stop building). Do P0 before P1, P1 before P2. Integrate frontend and backend on the same working path each time; no isolated halves.

## Code conventions

- Match the surrounding code's style and comment density.
- Backend: type-annotate everything; AI outputs are Pydantic models, never raw dicts.
- Prompts are plain text files in `backend/prompts/`, one per service; they must cite evidence, keep the principle the same in follow-ups, and never reveal the full answer in Master.
- Use `hashlib`/`random` from the standard library for repeat detection and experiment selection; strategy choice is rule-based, not a learning algorithm.
