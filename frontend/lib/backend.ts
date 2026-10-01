/* Turns what the backend knows into what the Progress screens show, and records a Master session on the backend. */

import { api, isVerdictTurn, MARIA_ID, type LearnerView, type StrategyRow as ApiStrategyRow, type StrategyView, type VerdictChanges } from "./api";
import { POLICY, type StrategyRow } from "./progress-data";
import type { MasterSession, StudentInput, TutorService, Turn } from "./tutor/types";

// Names for the backend's strategies, in the words the screens use.
const STRATEGY_NAME: Record<string, string> = {
  socratic: "Socratic questions",
  visual_decomposition: "Visual + Socratic",
  worked_example: "Worked example",
  analogy: "Analogy",
  counterexample: "Counterexample",
  representation_switch: "Representation switch",
  micro_hint: "Micro-hint",
};

// The scripted scenario's gap ("words → equation") is a recognition gap on the backend.
export const GAP_LABEL: Record<string, string> = { recognition: "Words → equation" };

// Backend concept names that have a node on the constellation.
export const CONCEPT_NODE: Record<string, string> = { "Constant-acceleration kinematics": "kin" };

/** Strategy rows from the backend, by gap label. Only gaps the screens know about are returned. */
export function policyFromStrategies(view: StrategyView): Record<string, StrategyRow[]> {
  const out: Record<string, StrategyRow[]> = {};
  for (const row of view.rows as ApiStrategyRow[]) {
    const label = GAP_LABEL[row.gap];
    if (!label || !(label in POLICY)) continue;
    (out[label] ??= []).push({ s: STRATEGY_NAME[row.method] ?? row.method, a: row.independent_successes, n: row.uses });
  }
  for (const rows of Object.values(out)) rows.sort((x, y) => y.a / y.n - x.a / x.n);
  return out;
}

export type BackendData = { learner: LearnerView; strategies: StrategyView };

/** Read Maria's two views. Returns null when the backend is not reachable. */
export async function loadBackendData(): Promise<BackendData | null> {
  try {
    const [learner, strategies] = await Promise.all([api.learner(MARIA_ID), api.strategies(MARIA_ID)]);
    return { learner, strategies };
  } catch {
    return null;
  }
}

/**
 * Wraps a tutor so that a Master session is also recorded on the backend: the backend keeps the
 * attempts, the diagnosis and, when the fresh problem is solved, the outcome and the concept and
 * strategy updates. If the backend is unreachable nothing changes on screen.
 */
export function recordedTutor(inner: TutorService, onVerdict: (changes: VerdictChanges) => void): TutorService {
  return {
    source: inner.source,
    answer: (problem) => inner.answer(problem),
    async begin(problem) {
      const { session, turn } = await inner.begin(problem);
      const backendSession = api.startSession(problem, MARIA_ID).then((s) => s.session_id).catch(() => null);
      return { session: new RecordedSession(session, backendSession, onVerdict), turn };
    },
  };
}

// The student inputs the backend should see: the first idea, the warm-up and the fresh problem.
const RECORDED = new Set(["idea", "probe", "transfer"]);

class RecordedSession implements MasterSession {
  constructor(
    private inner: MasterSession,
    private backendSession: Promise<string | null>,
    private onVerdict: (changes: VerdictChanges) => void,
  ) {}

  async send(input: StudentInput): Promise<Turn> {
    const turn = await this.inner.send(input);
    if (turn.accepted && input.kind && RECORDED.has(input.kind)) void this.record(input);
    return turn;
  }

  private async record(input: StudentInput) {
    const id = await this.backendSession;
    if (!id) return;
    const text = input.answer ? `${input.text} (answer: ${input.answer})` : input.text;
    try {
      const reply = await api.attempt(id, text);
      if (isVerdictTurn(reply) && reply.verdict.result === "VERIFIED") this.onVerdict(reply.verdict.changes);
    } catch {
      // Recording is best effort: the screens keep working without the backend.
    }
  }
}

/** Seeded strategy rows replaced by the backend's, when it is reachable. */
export const livePolicy = (data: BackendData | null) => (data ? policyFromStrategies(data.strategies) : undefined);
