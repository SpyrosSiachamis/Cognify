/* The frontend's only door to the backend. It never talks to a model provider or to the database.
   The shapes mirror the backend's Pydantic models (docs/API_CONTRACT.md); the backend is the source of truth,
   so this file adapts to it and never the other way round. */

import type { Confidence, DecisionMode, GapType, Phase, State, StepRole, StepStatus, Strategy } from "./vocab";

// Set at build time (docker-compose.yml sets it for the dev container). The fallback is the local backend.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// The seeded demo learner (fixed UUID from docs/API_CONTRACT.md; app/seed on the backend).
export const MARIA_ID = "16e82ef2-adee-4671-8393-c6b50ac91672";

// ---- learner views: GET /api/learner/{id}, GET /api/strategies/{id} ----

export type LearnerConcept = { concept_id: string; name: string; state: State; evidence: string[] };
export type LearnerView = { student_id: string; display_name: string; is_seeded: boolean; concepts: LearnerConcept[] };
export type StrategyRow = { gap: GapType; method: Strategy; uses: number; independent_successes: number; experiments: number };
export type MethodTotal = { method: Strategy; uses: number; independent_successes: number };
export type StrategyView = { student_id: string; display_name: string; is_seeded: boolean; rows: StrategyRow[]; methods: MethodTotal[] };

// ---- Master session: POST /api/session, /attempt, /exit ----

export type SessionStartResponse = { session_id: string; phase: Phase; message: string; hints_used: number };

export type Step = { role: StepRole; status: StepStatus; quote: string | null };
export type Alternative = { gap: GapType; confidence: Confidence };
export type DiagnosisView = { steps: Step[]; main_gap: GapType | null; alternatives: Alternative[]; confidence: Confidence };
export type MethodView = { name: Strategy; mode: DecisionMode; experiment: boolean; reason: string };
export type ReplyCheckView = { approved: boolean; summary: string };
export type TutorTurn = {
  session_id: string;
  phase: Phase; // "teach" or "stress_test"
  message: string;
  diagnosis?: DiagnosisView | null;
  method?: MethodView | null;
  follow_up?: { problem: string } | null;
  hints_used: number;
  reply_check: ReplyCheckView;
};

export type Counts = { uses: number; independent_successes: number };
export type VerdictChanges = {
  concept: { concept_id: string; name: string; before: State; after: State };
  strategy?: { gap: GapType; method: Strategy; before: Counts; after: Counts } | null; // null when no method was used
};
export type Verdict = { result: "VERIFIED" | "NOT YET"; evidence: string; independent: boolean; remaining_gap: GapType | null; changes: VerdictChanges };
export type VerdictTurn = { session_id: string; phase: "verdict"; session_over: boolean; message?: string | null; verdict: Verdict };
export type AttemptResponse = TutorTurn | VerdictTurn;
export const isVerdictTurn = (r: AttemptResponse): r is VerdictTurn => r.phase === "verdict" && "verdict" in r;

export type Solution = { result: string; steps: string[] };
export type ExitResponse = { phase: "exited"; solution: Solution; evidence_recorded: boolean };

// ---- errors ----

/** Every failure, in the backend's error shape (`{error: {code, message, retryable}}`) or a client-side one. */
export class ApiError extends Error {
  constructor(
    readonly code: string, // the backend's code, or "network", "timeout", "malformed_response"
    message: string,
    readonly retryable: boolean,
    readonly status?: number,
  ) {
    super(message);
  }
}

// How long to wait. A turn can take several model calls (each limited to 60 s on the backend), so be generous.
const TIMEOUT_MS = { read: 15_000, start: 120_000, turn: 240_000 };

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const isStr = (v: unknown): v is string => typeof v === "string";
const isNum = (v: unknown): v is number => typeof v === "number";

/** Turn a non-2xx response into an ApiError, reading the backend's error shape when it is there. */
async function errorFrom(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {}
  const e = isObj(body) && isObj(body.error) ? body.error : null;
  if (e && isStr(e.code) && isStr(e.message)) return new ApiError(e.code, e.message, e.retryable === true, res.status);
  return new ApiError("http_error", `The server answered ${res.status}.`, res.status >= 500, res.status);
}

async function call<T>(path: string, timeout: number, check: (v: unknown) => v is T, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), timeout);
  const onAbort = () => controller.abort("cancelled");
  signal?.addEventListener("abort", onAbort);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal, headers: { "Content-Type": "application/json", ...init?.headers } });
  } catch {
    if (controller.signal.reason === "timeout") throw new ApiError("timeout", "Cognify took too long to answer.", true);
    if (controller.signal.reason === "cancelled") throw new ApiError("cancelled", "The request was cancelled.", false);
    throw new ApiError("network", "Cannot reach the Cognify backend.", true);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
  if (!res.ok) throw await errorFrom(res);
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new ApiError("malformed_response", "The backend sent a response that is not JSON.", false, res.status);
  }
  if (!check(body)) throw new ApiError("malformed_response", `The backend's response to ${path} has an unexpected shape.`, false, res.status);
  return body;
}

// ---- response checks: just the fields the screens rely on ----

const isStep = (v: unknown): v is Step => isObj(v) && isStr(v.role) && isStr(v.status) && (v.quote === null || v.quote === undefined || isStr(v.quote));
const isDiagnosis = (v: unknown): v is DiagnosisView =>
  isObj(v) && Array.isArray(v.steps) && v.steps.every(isStep) && Array.isArray(v.alternatives) && isStr(v.confidence) && (v.main_gap === null || isStr(v.main_gap));
const isMethod = (v: unknown): v is MethodView => isObj(v) && isStr(v.name) && isStr(v.mode) && typeof v.experiment === "boolean" && isStr(v.reason);
const isCounts = (v: unknown): v is Counts => isObj(v) && isNum(v.uses) && isNum(v.independent_successes);

export const checks = {
  start: (v: unknown): v is SessionStartResponse => isObj(v) && isStr(v.session_id) && isStr(v.phase) && isStr(v.message) && isNum(v.hints_used),
  attempt: (v: unknown): v is AttemptResponse => {
    if (!isObj(v) || !isStr(v.session_id) || !isStr(v.phase)) return false;
    if (v.phase === "verdict") {
      const d = v.verdict;
      return (
        typeof v.session_over === "boolean" && isObj(d) && (d.result === "VERIFIED" || d.result === "NOT YET") && isStr(d.evidence) &&
        typeof d.independent === "boolean" && isObj(d.changes) && isObj(d.changes.concept) &&
        (d.changes.strategy == null || (isObj(d.changes.strategy) && isCounts(d.changes.strategy.before) && isCounts(d.changes.strategy.after)))
      );
    }
    return (
      isStr(v.message) && isNum(v.hints_used) && isObj(v.reply_check) && typeof v.reply_check.approved === "boolean" &&
      (v.diagnosis == null || isDiagnosis(v.diagnosis)) && (v.method == null || isMethod(v.method)) &&
      (v.follow_up == null || (isObj(v.follow_up) && isStr(v.follow_up.problem))) &&
      (v.phase !== "stress_test" || isObj(v.follow_up))
    );
  },
  exit: (v: unknown): v is ExitResponse => isObj(v) && v.phase === "exited" && isObj(v.solution) && isStr(v.solution.result) && Array.isArray(v.solution.steps),
  learner: (v: unknown): v is LearnerView =>
    isObj(v) && isStr(v.display_name) && typeof v.is_seeded === "boolean" && Array.isArray(v.concepts) &&
    v.concepts.every((c) => isObj(c) && isStr(c.name) && isStr(c.state) && Array.isArray(c.evidence)),
  strategies: (v: unknown): v is StrategyView =>
    isObj(v) && typeof v.is_seeded === "boolean" && Array.isArray(v.rows) &&
    v.rows.every((r) => isObj(r) && isStr(r.gap) && isStr(r.method) && isNum(r.uses) && isNum(r.independent_successes)) && Array.isArray(v.methods),
};

const post = (body?: unknown): RequestInit => ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  learner: (id: string) => call(`/api/learner/${id}`, TIMEOUT_MS.read, checks.learner),
  strategies: (id: string) => call(`/api/strategies/${id}`, TIMEOUT_MS.read, checks.strategies),
  startSession: (problem: string, studentId: string, signal?: AbortSignal) =>
    call("/api/session", TIMEOUT_MS.start, checks.start, post({ problem, student_id: studentId, force_experiment: false }), signal),
  attempt: (sessionId: string, text: string, signal?: AbortSignal) =>
    call(`/api/session/${sessionId}/attempt`, TIMEOUT_MS.turn, checks.attempt, post({ text }), signal),
  exit: (sessionId: string) => call(`/api/session/${sessionId}/exit`, TIMEOUT_MS.read, checks.exit, post()),
};
