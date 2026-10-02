# Cognify

Cognify is a problem-solving tutor that learns how a student thinks, and keeps testing whether its own best teaching method is still the best.
In **Master** mode it asks first, splits the student's answer into steps, finds the exact step that breaks (quoting the student's own words), teaches with the method that has worked for that student (sometimes trying another and saying so), then sets a fresh problem with no help. Code, not the model, decides **VERIFIED**.
Only **Level 1 (Answer)** and **Level 5 (Master)** are in scope. `SPEC.md` is the source of truth for scope, `CLAUDE.md` for the rules everyone follows.

## Status

Working end to end with the real model and with the offline story: the Master loop (first thought, diagnosis, method choice, one teaching move, personal follow-up, verdict), the two learners Maria and Nikos with seeded demo history, the Understanding Map and How You Learn views.
Not built yet: the Level 1 endpoint (`POST /api/answer`), a persistent database (history lives in memory, so a backend restart resets everything), and a public deployment. There is no live demo address yet (F28).

## Run it

You need Docker Compose (this team uses Colima; if published ports are unreachable from the host, run `colima restart`).

```bash
cp .env.example .env            # then edit it, see below
docker compose up --build       # db :5432, backend :8000, frontend :3000
curl localhost:8000/api/health  # {"status":"ok"}   (/health works too)
```

Open http://localhost:3000. The backend's API docs are at http://localhost:8000/docs.

**Pick the tutor in `.env`.** A fresh copy of `.env.example` turns the real tutor on, and the backend refuses to start without AWS keys:

| You want | Set in `.env` |
|---|---|
| The saved Maria and Nikos story, no keys, no network, no cost | `DEMO_MODE=offline` |
| The real tutor (Bedrock, Mistral Large 3) | `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` (or `AWS_BEARER_TOKEN_BEDROCK`), `AWS_REGION=us-east-1`, `TUTOR_MODEL_ID` as in the example. That model id is not valid in `eu-central-1`. |

After editing `.env` run `docker compose up -d backend`; a plain restart does not reload it. Never commit `.env` (it is gitignored) or print real keys.
Offline mode always plays the saved ball story, whatever problem is pasted. It is a rehearsal, not a solver.

If a frontend command says `vitest: not found` (or another package is missing) after pulling, the container's `node_modules` is a Docker volume that predates the change. Renew it with `docker compose up --build -V frontend`.

Without Docker: `cd backend && pip install -r requirements.txt`, export the variables from `.env`, then `uvicorn app.main:app --reload` (Python 3.13). Frontend: `cd frontend && npm install && npm run dev`.

### Other settings

| Variable | What it does |
|---|---|
| `CORS_ORIGINS` | Comma separated frontend addresses allowed to call the API. Empty means `http://localhost:3000` and `http://127.0.0.1:3000`. `*` is refused. Set it for any other address, for example a phone on the same network, and set `NEXT_PUBLIC_API_URL` so the page does not call `localhost`. |
| `DEBUG_TRACE` | Development only. Serves `/api/debug-trace`, which holds hidden solutions and student text. The local Docker stack turns it on by default. Never enable it on a public deployment. |
| `STORAGE`, `AUTOSEED` | `memory` is the only store for now. `AUTOSEED=true` loads the seeded history at startup. |

## Seeded demo history

Maria (a recognition gap, `visual_decomposition` 7 of 9) and Nikos (a procedure gap, `worked_example` 5 of 6) start with history that is always labelled **"seeded demo history"**.
`cd backend && python -m app.seed show` prints it. To reset the demo, restart the backend: the memory store reloads the seed at startup.

## Tests

```bash
cd backend && python -m pytest -q          # backend; the live-model tests are skipped
cd backend && python -m pytest -m live     # calls the real model: needs keys, slow, costs money
cd frontend && npm test && npm run lint && npm run build
```

Run them after every change. The demo script plays a whole session through a running backend:

```bash
python demo/play_story.py                  # Maria and Nikos against localhost:8000, the exact offline story
python demo/play_story.py --shape-only     # with the real model: checks consistency, accepts VERIFIED or NOT YET
```

It plays real sessions, so it changes the counts (restart the backend afterwards), and it refuses non-local addresses unless you pass `--allow-remote`.

## Live demo

`docs/DEMO.md` has the script, the 90-second pitch and the pre-flight checklist. For the live demo start the backend with the production override, so saving a file cannot restart it and wipe open sessions:

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build backend
```

## API

All routes are under `/api`; the Pydantic models (shown at `/docs`) are the contract and `docs/API_CONTRACT.md` explains the behaviour. Errors always look like `{"error": {"code", "message", "retryable"}}`.

| Route | Purpose |
|---|---|
| `POST /api/session` | Start a Master session |
| `POST /api/session/{id}/attempt` | The one student-facing turn: a teaching reply, the fresh problem, or the verdict |
| `POST /api/session/{id}/exit` | Leave Master, see the solution, record no evidence |
| `GET /api/learner/{id}`, `GET /api/strategies/{id}` | The two views: Understanding Map and How You Learn |

## Layout

```
frontend/             Next.js app (App Router, TypeScript, Tailwind)
backend/app/          FastAPI app: user (flow and routes), session (API models), tutor, verification,
                      ai_gateway (the only door to the model), history (the only door to storage),
                      seed, common (shared vocabulary)
backend/tests/        pytest
demo/                 play_story.py, the story rehearsal
docs/                 ARCHITECTURE, API_CONTRACT, DATA, PROMPTS, SCREENS, DEMO, evaluation reports
SPEC.md, CLAUDE.md    scope, and the rules for anyone writing code (human or AI)
```

Start with `docs/ARCHITECTURE.md` before touching the backend.

## Who owns what

| Area | Owner |
|---|---|
| Tutor agent, verification, AI gateway, history | _add name / GitHub handle_ |
| Frontend | _add name / GitHub handle_ |
| User module (session flow and routes), demo tooling | _add name / GitHub handle_ |

Open a pull request into `main`; do not push to `main` directly.
