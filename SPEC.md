# Cognify: Feature Spec (FuturEd AI 2026)

What we build, in what order, and what we leave alone. This is the single source of truth for scope.

## Definition

Cognify is a problem-solving tutor that learns how you think, and keeps testing whether its own best guess is still the best. It works for general subjects, not one specific subject.

**Scope of levels:** we build only **Level 1 (Answer)** and **Level 5 (Master)**. Levels 2, 3 and 4 are not built.

The student pastes a problem and chooses how deep they want help (Level 1: Answer, or Level 5: Master). In **Master mode**, Cognify splits their answer into reasoning steps, finds the gap, teaches with the method that has worked for them, sometimes tries a different one, then gives a fresh follow-up built from their reasoning. It only calls the concept understood when they solve it without help.

### Idea A: Find the best method, keep exploring
Cognify remembers which teaching method led to independent success for this student and this kind of gap. It uses that method most of the time, but deliberately tries a different one now and then, even if the best one has worked before, and records what happened.

### Idea B: Same problem, different follow-up
Two students can paste the same problem. Each answer is cut into steps, so the follow-up problem targets that student's weakest step and reasoning. The method may differ, and the secondary problem must differ too.

## How to use this spec

- Every feature has an ID. If it has no ID here, we do not build it. New ideas go to the Parked list first.
- Build in priority order.
  - **P0:** the demo breaks without it.
  - **P1:** makes the demo stronger; start only when the P0 loop works end to end.
  - **P2:** only if everything else is stable.
  - **Parked:** not this hackathon.
- Area says who owns it: **FE** frontend, **AI** prompts and logic behind the app, **DATA** Supabase and what the app remembers, **PITCH** demo, tests and fallback.
- Each feature has a **Done when** line. If it is true, stop polishing and move on.

## Decisions to settle before coding starts

| Question | Decision |
|---|---|
| Product name | **Cognify.** Update the mockups to match. |
| Hero demo problem: ball thrown upward or rectangle (area 48)? | Use the ball. The screens already exist and it has a clear two-way split (section 5). It is only the demo problem; the product itself is subject-agnostic. |
| Colour of green | Green is used **only** for VERIFIED. Main buttons use a non-green colour (navy and gold from the mockups). |
| Levels | Build Level 1 and Level 5 only. The depth selector shows just those two cards. |

## 1. Features: entry and the two levels

Screens from the mockups: Problem Inbox, Depth Selector and Level 1 Answer. Only Levels 1 and 5 are built.

| ID | Feature | What it does | Done when | Pri | Area |
|---|---|---|---|---|---|
| F1 | Problem Inbox | Paste or type a problem (2000 characters), optional subject chips (Math, Physics, Biology, Chemistry, Other), "Try an example". | The example loads in one click and Continue opens the Depth Selector. | P0 | FE |
| F2 | Depth Selector | Two cards (Answer and Master) with one line of intent each, selected card highlighted, "Edit problem". No cards are shown for the unbuilt levels. | A judge understands the two levels in under 15 seconds. | P0 | FE |
| F3 | Level 1: Answer | Final result plus short steps, formulas rendered cleanly. Shows the note that this does not count as mastery evidence. Only button: Switch to Master. | Answer appears fast and nothing about the learner changes. | P1 | AI, FE |

## 2. Features: Master mode, the core loop

This is the product. Everything here is P0 and it is what the judges will watch.

| ID | Feature | What it does | Done when | Pri | Area |
|---|---|---|---|---|---|
| F6 | First-thought capture | Master asks "What would you try first?" before any help. If the student writes nothing useful, it asks one short question instead of explaining. | There is no way to reach the full solution from Master without choosing to leave Master. | P0 | FE, AI |
| F7 | Answer splitting | Every student answer is cut into ordered steps (identify quantities, choose method, set up, substitute, compute, interpret). Each step is marked correct, wrong or missing, with the student's own words as evidence. | The Gap Reveal can point at one specific step and quote it. | P0 | AI |
| F8 | Reasoning read-out | Rates the response as Strong, Fragile, Weak or Untested on: correctness, recognition, representation, concept, procedure, strategy choice, self-correction, hint dependency, transfer. Each rating cites evidence. No made-up percentages. | UI shows at least the 3 to 5 most relevant dimensions with a quote each. | P0 | AI, FE |
| F9 | Active diagnosis and Gap Reveal | Keeps two or three possible explanations. If unsure, asks one 10-second probe to tell them apart. Then shows the main gap with evidence and confidence, in a warm tone that does not shame. | Same wrong answer, two different causes: the probe separates them in the demo. | P0 | AI, FE |
| F10 | Teaching strategy library | Socratic questions, visual decomposition, worked example, analogy, counterexample, representation switch, micro-hint. | Minimum 4 working: Socratic, visual, worked example, micro-hint. The rest are P1. | P0 | AI |
| F11 | Best-method choice | Picks the strategy with the best verified record for this student and gap type, and says why on screen ("Worked 7 of 9 times for you"). New students start from sensible defaults. The method is returned by the `choose_strategy` tool and recorded by the app. | Seeded history visibly changes which strategy is chosen. | P0 | AI, DATA |
| F12 | Exploration | Sometimes picks an untried, thinly tested or out-of-date strategy even when another has worked, and tells the student it is an experiment. The result counts as evidence like any other. The method is returned by the `choose_strategy` tool and recorded by the app. | A demo switch forces an experiment; it never happens during verification. | P0 | AI, DATA |
| F13 | One small teaching move | Gives the smallest useful question or hint, then waits for the student. Goal: fewer and smaller hints over time. | No teaching turn gives more than one new idea. | P0 | AI |
| F14 | Personal follow-up problem | Builds the secondary problem from this student's own answer: their weakest step, their diagnosed gap, and how far their understanding survives changes. Keeps the same underlying principle. Never repeats a problem they have seen. | Two students with the same problem get different follow-ups (section 5). | P0 | AI |
| F15 | Stress test | A fresh problem with no hints and no scaffolding, changing at least one thing: wording, representation, context or distractors. | It looks different from the first problem but needs the same principle. | P0 | AI, FE |
| F16 | Verification | Shows VERIFIED or NOT YET with evidence. Judges independence separately from correctness. If NOT YET, updates the diagnosis and changes approach instead of repeating. A correct and independent first thought goes straight to the follow-up. VERIFIED is decided by code from the verifier's judgement, the hint count and freshness. | A lucky correct answer after many hints is not marked VERIFIED. | P0 | AI, FE |
| F17 | Learning from the outcome | After each loop the app remembers which strategy was used, whether it led to independent success, hints used, and the before and after state of the concept. | The next session picks differently because of the last one. | P0 | DATA |

## 3. Features: making both learners visible

The student learns the concept, and Cognify learns how to teach that student. The judges must be able to see both change.

| ID | Feature | What it does | Done when | Pri | Area |
|---|---|---|---|---|---|
| F18 | Understanding Map | Concepts shown as Strong, Fragile, Weak, Untested or Verified, each with its evidence. Lives under My Learning. | The demo concept moves from Fragile to Verified on screen. | P0 | FE |
| F19 | How You Learn | Which teaching methods worked for which kinds of gaps (e.g. "Visual + Socratic: 7 of 9"), with experiments marked. Shows observed results only, never labels like "visual learner". | The count updates right after verification (7/9 becomes 8/10). | P0 | FE |
| F20 | Breaking-point view | A chart of where understanding stops holding: same problem, different numbers, different representation, different context, distractors, combined concepts. | A radar or ladder with at least four steps filled in. | P1 | FE |
| F21 | Signature animation | At the end of verification the concept turns Verified while the strategy count ticks up, in one moment. | Both change at the same time and it is smooth on a projector. | P1 | FE |
| F22 | Same problem, two learners | A scripted comparison (Maria and Nikos) showing identical problems leading to different diagnoses, strategies and follow-ups. | One screen or slide a judge can read in 20 seconds. | P1 | FE, PITCH |
| F23 | Sidebar pages | My Learning (holds F18 and F19). History, Concept Map and Profile from the mockups. | My Learning works. The other three are hidden or show a short placeholder. | P0 | FE |

## 4. Features: platform and reliability

| ID | Feature | What it does | Done when | Pri | Area |
|---|---|---|---|---|---|
| F24 | Seeded demo history | A believable starting history for Maria so strategy choice and the maps have something to show. Clearly labelled "seeded demo history". | Nothing synthetic is ever shown as real. | P0 | DATA |
| F25 | Safe AI output | Every AI answer the app relies on is checked before use, with one retry and then a safe fallback. Calls have time limits. | A broken AI reply never crashes a screen. | P0 | AI |
| F26 | One AI doorway | All AI calls go through one place in the backend so the model can be swapped. The frontend never talks to the provider. | Changing the model touches one file. | P0 | AI |
| F27 | Offline demo path | A rehearsed, pre-saved version of the full Maria story that runs with no network or AI. | One switch plays the whole story start to finish. | P0 | PITCH |
| F28 | Public deployment | The app runs at a public address and works from a second device. | The full demo works from a phone on mobile data. | P1 | PITCH |
| F29 | Tests | Backend: strategy choice, exploration rules, follow-up never repeating, verification updates. Frontend: depth selection and one full-flow check. | Tests pass before every merge to main. | P1 | AI, PITCH |
| F30 | Reply guard | Every Master reply and follow-up is checked for the answer, a heavy hint and method drift before it is sent. A rejected one is regenerated with the reason up to 2 times, then a safe fallback is sent. | A reply that states the answer never reaches the student. | P0 | AI |

## 5. The Master loop, step by step

Reference path for the demo and for building F6-F17 in the right order.

| # | What happens | Features |
|---|---|---|
| 1 | Student pastes a problem and picks Master | F1, F2 |
| 2 | Cognify asks what they would try first (no help yet) | F6 |
| 3 | Answer is split into steps and read for evidence | F7, F8 |
| 4 | Two possible causes; one short probe tells them apart | F9 |
| 5 | Gap Reveal: main cause, evidence, confidence | F9 |
| 6 | Pick a method from history, or run an experiment, and say which | F11, F12 |
| 7 | One small teaching move; student builds the missing step | F13 |
| 8 | Support removed. Follow-up built from this student's own answer | F14, F15 |
| 9 | Student solves alone. VERIFIED or NOT YET with evidence | F16 |
| 10 | Both views update; the result is remembered for next time | F17, F18, F19, F21 |

### Exploration rules (F12)

- Mostly use the best method. About one Master session in five tries a different one.
- **Untried first.** A method never used for this kind of gap is the preferred experiment.
- **Old evidence expires.** If the best method's last success was long ago (about a month), another gets a fair chance.
- **Never in the test.** Experiments happen while teaching, not during verification.
- **Fail safe.** If an experiment does not work, return to the best method in the same session. Never experiment twice in a row on the same gap.
- **Be honest on screen.** Say "Trying something different this time". A failed experiment is still useful evidence.

### Follow-up rules (F14): same problem, different secondary problem

| | Maria | Nikos |
|---|---|---|
| Same problem | Ball thrown up at 20 m/s. How high does it go? (g = 9.8) | Ball thrown up at 20 m/s. How high does it go? (g = 9.8) |
| What the answer shows | Finds the time to the top, then stops: "I don't know how to get height from time." | Picks the right equation but writes the sign wrong and gets a negative height. |
| Weakest step | Choose the method (recognition) | Carry out the procedure (signs) |
| Method | Visual decomposition, or an experiment | Worked example with steps faded |
| Their follow-up | A stone launched upward at 15 m/s from a balcony; how far above it does it rise? No time given, so she must choose the equation without time. | A ball thrown down at 5 m/s from 30 m; speed at the ground? Same equation, but now signs matter. |

- Keep the principle the same; change the surface in the direction that tests this student's weakest step.
- Pick the next harder change they have not yet survived, and set difficulty from how solid they currently are.
- Check against everything this student has already seen. If it repeats, generate again.

## 6. Build order and scope guardrails

| Milestone | Done when | Features |
|---|---|---|
| M0 Repo and health | Frontend opens, backend answers, one request crosses between them. | F26 |
| M1 Hardcoded slice | Problem to Level 5 to fixed diagnosis, fixed teaching, fixed verification, VERIFIED screen. No live AI. | F1, F2, F6, F9, F15, F16 |
| M2 Real diagnosis | One live AI call returns a checked diagnosis built from split steps. | F3, F7, F8, F9, F25 |
| M3 Adaptive teaching | Strategy is chosen from seeded history, can run an experiment, and the teaching move is generated live. | F10-F13, F24, F30 |
| M4 Follow-up and verifier | Personal follow-up generated from the student's answer; independent attempt judged. | F14, F15, F16 |
| M5 Memory | Session outcome and strategy result are saved and used next time. | F17 |
| M6 Two-learner views | Understanding Map and How You Learn change after verification. | F18, F19, F20, F21, F23 |
| M7 Reliability | Timeouts, fallback, offline path, public deployment tested from another device. | F25, F27, F28, F29 |
| M8 Stop building | Rehearse, remove fragile extras, prepare judge answers. | F22 if time |

### Parked: do not build this hackathon

| Parked | Why |
|---|---|
| Levels 2, 3 and 4 (Explain, Teach, Coach); IDs F4 and F5 are retired | Only Levels 1 and 5 are built. No cards are shown for them. |
| Course PDF upload and answers grounded in course material | Large and not part of the closed loop. |
| Finding similar past sessions by meaning (vector search) | Simple counts per method and gap are enough for the demo. |
| Concept dependency graphs | Not part of the closed loop. |
| Teacher dashboard, login polish | Single demo user is fine. |
| Advanced learning algorithm for method choice | Rule-based choice plus the exploration rules is explainable and debuggable. |
| Retention checks days later, teach-back, voice, handwriting | Roadmap slide only. |

### Scope guardrails

- The loop beats the feature count. A flawless F6-F19 is worth more than a half-built course platform.
- Nothing new without an ID. Ideas are written under Parked with a one-line reason, and decided at the next check-in.
- Integrate every 60-90 minutes. Frontend and backend meet on the same working path each time; no isolated halves.
- Preserve the demo path. After every change the Maria story must still run end to end. Level 1 never counts as evidence.
- Honest claims. Say "inspired by Dream-RSI", "observed strategy effectiveness", "evidence-backed diagnosis". Never "learning styles".

## 7. Tools

| Area | Tool | Used for |
|---|---|---|
| Frontend | Next.js (App Router) + TypeScript | The app and every screen. File-based routing covers Home, level screens, My Learning and the sidebar. |
| Styling | Tailwind CSS + shadcn/ui | Cream cards, library look from the mockups. |
| App state | Zustand | A small state machine so the Master loop is predictable (F6-F16). |
| Server calls | TanStack Query | Loading and retrying calls to the backend. |
| Math | KaTeX | Rendering equations like v² = u² - 2gh. |
| Charts | Recharts | Understanding and strategy views (F18-F20). |
| Motion | Framer Motion | The signature animation (F21). |
| Backend | Python 3.13 + FastAPI + Uvicorn | Runs the loop and talks to the AI. |
| Validation | Pydantic v2 | Checks every AI reply before the app uses it (F25). |
| AI | Pydantic AI on AWS Bedrock (EU region), behind one gateway | All AI calls (F26). |
| Database | Supabase (PostgreSQL) + Supabase CLI | What the app remembers (F17, F24). |
| Math helpers | Python standard library (hashlib, random) | Spotting repeated problems and choosing experiments. |
| Containers | Docker Compose (db, backend, frontend) | Local development. |
| Tests | pytest, Vitest + React Testing Library, Playwright (optional) | F29 and the full-demo check. |
| Code and team | Git + GitHub, CLAUDE.md / AGENTS.md | Version control and small coding tickets. |
| Hosting | Vercel (frontend), Render or Railway (backend), Supabase (database) | Public demo address (F28). |
| Optional | pgvector, PyMuPDF, Figma | Only after the P0 loop works; both are Parked. |

## 8. Repository layout

The app lives in `frontend/` and `backend/` at the repo root.

```
futureed/
|-- AGENTS.md, CLAUDE.md   rules for anyone writing code
|-- SPEC.md                this document
|-- README.md
|-- docs/                  ARCHITECTURE, API_CONTRACT, DATA, PROMPTS, SCREENS,
|                          DEMO
|-- frontend/              Next.js app
|   `-- routes: Home, Level 1, Level 5 (Master), My Learning + placeholders
|   `-- components: DepthSelector, StepList, GapReveal, HintPanel,
|                   VerifiedBadge, UnderstandingMap, HowYouLearn
|   `-- features: session (loop), learner-model, strategy-view
|   `-- lib: backend client, math helpers
|-- backend/
|   |-- app/               entry point, routes, checked data shapes
|   |   `-- services/      ai_gateway, tutor, strategy_choice,
|   |                      novelty, verification, history
|   |-- prompts/           one text prompt per service
|   `-- tests/
|-- supabase/              database setup and seeded demo history
`-- demo/                  Maria story, offline fallback, pitch notes
```

## 9. What each .md file should contain

Short and authoritative. If a teammate or an AI coding tool has a question, one of these files should answer it.

| File | Should contain |
|---|---|
| AGENTS.md / CLAUDE.md | Rules for anyone writing code, human or AI: demo reliability beats features; never use an AI answer without checking it; no provider keys or provider calls in the frontend; Master never reveals the full answer; every diagnosis quotes student evidence; the teaching method comes from the `choose_strategy` tool and is recorded; every experiment is labelled; every Master reply and follow-up is verified before it is sent; code, not the model, decides VERIFIED; Level 1 writes nothing; seeded data is always labelled; no feature without an ID in SPEC.md; run tests after each change; keep the Maria story working. |
| SPEC.md | The single source of truth for scope: the definition, Ideas A and B, the two levels (Answer and Master), the feature table with IDs, priorities and done-when lines, the Master loop, milestones, the Parked list and guardrails. |
| README.md | What Cognify is in three lines, how to run it locally (Docker Compose, `.env`, health check), how to load the seeded demo history, how to run tests, the live demo address and who owns what. |
| docs/ARCHITECTURE.md | How the backend works: the tutor agent, the verification LLM and its three modes, what is code and what is AI, the session phases, the `choose_strategy` rules and exploration settings, the retry caps and fallbacks, and what each side can see. |
| docs/API_CONTRACT.md | The agreement between frontend and backend: endpoints under `/api`, one JSON example per request and response, the allowed values, the error shape, demo mode, and the contracts between backend pieces (strategy tool, tutor agent output, verifier result). All IDs are UUIDs. Exact field types come from the Pydantic models. |
| docs/DATA.md | A plain-language list of what the app remembers and why, tied to F11, F12, F17, F18, F19 and F24: when each thing is written, the concept-state moves, and what the seeded demo history for Maria and Nikos contains. The database setup itself lives in `supabase/`. |
| docs/PROMPTS.md | In plain words, one section per AI role (tutor agent, verifier): its job, its inputs, what it may and may not reveal, and its rules (cite evidence, low confidence means probe instead of label, one new idea per turn, keep the principle in follow-ups, reply in the student's language). It also holds the step names, the nine dimensions and the Strong / Fragile / Weak / Untested scale, with the ball problem worked through. |
| docs/SCREENS.md | Each phase and view mapped to a screen, including the Level 1 screen; the look from the mockups (library background, cream cards, serif headings, navy and gold buttons); colour meanings (green only for VERIFIED, amber in progress, warm red for gaps, never shaming); the seeded and reply-check badges; thinking, empty and error states. |
| docs/DEMO.md | The live demo script step by step, who clicks what, timings, the 90-second pitch, the judge Q&A, and how to switch to the offline path (F27). |

## Final check before the pitch

- A judge can understand the two levels in 15 seconds.
- Master never feels like an answer-dumping chatbot.
- The diagnosis shows evidence.
- Strategy choice visibly uses history, and an experiment is visibly labelled.
- Two students with the same problem get different follow-ups.
- The student succeeds without hints on the final problem.
- Both views update.
- Synthetic data is labelled.
- The offline path works.

If all true, stop adding features.
