/* The frontend's only door to the backend. It never talks to a model provider or to the database.
   Shapes follow docs/API_CONTRACT.md (the backend's Pydantic models are the source of truth). */

import type { Confidence } from "./vocab";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// The seeded demo learner (fixed UUID from the docs).
export const MARIA_ID = "16e82ef2-adee-4671-8393-c6b50ac91672";

export type ConceptView = { concept_id: string; name: string; state: string; evidence: string[] };
export type LearnerView = { student_id: string; display_name: string; is_seeded: boolean; concepts: ConceptView[] };
export type StrategyRow = { gap: string; method: string; uses: number; independent_successes: number; experiments: number };
export type StrategyView = { student_id: string; display_name: string; is_seeded: boolean; rows: StrategyRow[]; methods: { method: string; uses: number; independent_successes: number }[] };
export type Counts = { uses: number; independent_successes: number };
export type VerdictChanges = {
  concept: { concept_id: string; name: string; before: string; after: string };
  strategy: { gap: string; method: string; before: Counts; after: Counts };
};
export type Verdict = { result: "VERIFIED" | "NOT YET"; evidence: string; independent: boolean; remaining_gap: string | null; changes: VerdictChanges };
export type SessionStart = { session_id: string; phase: string; message: string; hints_used: number };
export type TutorTurn = { session_id: string; phase: string; message: string; hints_used: number; diagnosis?: { main_gap: string; confidence: Confidence } };
export type VerdictTurn = { session_id: string; phase: "verdict"; session_over: boolean; message?: string | null; verdict: Verdict };
export type AttemptResponse = TutorTurn | VerdictTurn;
export const isVerdictTurn = (r: AttemptResponse): r is VerdictTurn => "verdict" in r;

const TIMEOUT_MS = 4000;

/** The backend could not be reached (or answered with an error). Screens fall back to seeded data. */
export class BackendUnavailable extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
    if (!res.ok) throw new BackendUnavailable(`${path} answered ${res.status}`);
    return (await res.json()) as T;
  } catch (e) {
    throw e instanceof BackendUnavailable ? e : new BackendUnavailable(String(e));
  } finally {
    clearTimeout(timer);
  }
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  learner: (id: string) => call<LearnerView>(`/api/learner/${id}`),
  strategies: (id: string) => call<StrategyView>(`/api/strategies/${id}`),
  startSession: (problem: string, studentId: string) =>
    post<SessionStart>("/api/session", { problem, student_id: studentId, force_experiment: false }),
  attempt: (sessionId: string, text: string) => post<AttemptResponse>(`/api/session/${sessionId}/attempt`, { text }),
};
