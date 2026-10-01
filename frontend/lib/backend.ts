/* What the backend knows about the learner (GET /api/learner and /api/strategies), and the small
   selectors the screens use. Every value comes from these two views; nothing is filled in here. */

import { api, MARIA_ID, type LearnerConcept, type LearnerView, type StrategyRow, type StrategyView } from "./api";
import type { GapType } from "./vocab";

export type Views = { learner: LearnerView; strategies: StrategyView };

/** Read both views of the demo learner. Throws an ApiError when the backend cannot answer. */
export async function loadViews(studentId: string = MARIA_ID): Promise<Views> {
  const [learner, strategies] = await Promise.all([api.learner(studentId), api.strategies(studentId)]);
  return { learner, strategies };
}

/** Concepts the learner has proven (state "verified" on the backend). */
export const provenConcepts = (learner: LearnerView): LearnerConcept[] => learner.concepts.filter((c) => c.state === "verified");

export type GapGroup = { gap: GapType; rows: StrategyRow[]; best: StrategyRow | null };

// Same smoothing as the backend's choose_strategy ranking: (successes + 1) / (uses + 2), so one lucky use does not win.
const score = (r: StrategyRow) => (r.independent_successes + 1) / (r.uses + 2);

/** Strategy rows grouped by gap, best observed first. Gaps keep the backend's order of first appearance. */
export function strategyGroups(view: StrategyView): GapGroup[] {
  const groups = new Map<GapType, StrategyRow[]>();
  for (const row of view.rows) groups.set(row.gap, [...(groups.get(row.gap) ?? []), row]);
  return [...groups].map(([gap, rows]) => {
    const sorted = [...rows].sort((a, b) => score(b) - score(a) || b.uses - a.uses); // ties: more uses first, like the backend
    return { gap, rows: sorted, best: sorted.find((r) => r.uses > 0) ?? null };
  });
}
