/* The seeded demo history the Progress views and the result screen show (labelled "Seeded history" on screen).
   Same numbers and words as docs/cognify-prototype.html. */

export type Strength = "strong" | "fragile" | "weak" | "untested" | "verified";

export type StrategyRow = { s: string; a: number; n: number }; // name, independent successes, uses

export const POLICY: Record<string, StrategyRow[]> = {
  "Words → equation": [{ s: "Visual + Socratic", a: 7, n: 9 }, { s: "Worked example", a: 4, n: 7 }, { s: "Direct explanation", a: 2, n: 6 }],
  "Recognising the method": [{ s: "Counterexample", a: 5, n: 7 }, { s: "Analogy", a: 4, n: 6 }, { s: "Worked example", a: 3, n: 8 }],
  "Running the procedure": [{ s: "Worked example", a: 6, n: 8 }, { s: "Micro-hint", a: 5, n: 9 }, { s: "Socratic questions", a: 3, n: 7 }],
};

/** The strategy rows for one kind of gap, after today's verified win if there was one. */
export function policyNow(gap: string, verified: boolean): StrategyRow[] {
  const rows = POLICY[gap].map((r) => ({ ...r }));
  if (verified && gap === "Words → equation") {
    rows[0].a = 8;
    rows[0].n = 10;
  }
  return rows;
}

export const HINTS = { labels: ["Jun", "Jul", "Aug", "Sep 8", "Sep 22", "Today"], vals: [4, 3, 3, 2, 1, 0] };

export type ConceptNode = {
  id: string;
  label: string;
  x: number;
  y: number;
  big?: boolean;
  st: Strength;
  lad: (1 | 0 | null)[]; // one entry per rung: held, broke, or not tried
  ev: string;
  after?: { st: Strength; lad: (1 | 0 | null)[]; ev: string }; // what it becomes once today's transfer is verified
};

export const NODES: ConceptNode[] = [
  { id: "rat", label: "Ratios", x: 120, y: 110, st: "verified", lad: [1, 1, 1, 1, 0, null], ev: "Solved 5 of 5 problems, including a fresh one with extra information." },
  { id: "lin", label: "Linear equations", x: 150, y: 290, st: "verified", lad: [1, 1, 1, 1, 1, null], ev: "Holds across words, equations and graphs." },
  { id: "sys", label: "Systems", x: 215, y: 462, st: "untested", lad: [null, null, null, null, null, null], ev: "No evidence yet." },
  { id: "fac", label: "Factoring", x: 410, y: 150, st: "verified", lad: [1, 1, 1, 1, null, null], ev: "Verified on a fresh problem with one hint." },
  { id: "qf", label: "Quadratic formula", x: 620, y: 78, st: "fragile", lad: [1, 1, 0, null, null, null], ev: "Correct procedure, but hesitated on when to use it." },
  {
    id: "w2e", label: "Words → equation", x: 335, y: 352, st: "weak", lad: [1, 0, 0, null, null, null], ev: "Struggles to turn a verbal relation into algebra.",
    after: { st: "fragile", lad: [1, 1, 1, null, null, null], ev: "Built x(x + 2) = 48 with guidance, then transferred. One more independent success makes it verified." },
  },
  {
    id: "qm", label: "Quadratic modelling", x: 545, y: 305, big: true, st: "fragile", lad: [1, 1, 0, null, null, null], ev: "Algebra is fine. Stalled turning “2 m greater” into an equation.",
    after: { st: "verified", lad: [1, 1, 1, 1, null, null], ev: "Solved a fresh consecutive-even-numbers problem with 0 hints, today." },
  },
  { id: "area", label: "Area & perimeter", x: 360, y: 498, st: "strong", lad: [1, 1, 1, 0, null, null], ev: "Fluent with formulas. Weaker when a side is given only as a relation." },
  { id: "gp", label: "Graphing parabolas", x: 790, y: 215, st: "fragile", lad: [1, 0, null, null, null, null], ev: "Reads vertex form, loses track when the equation is expanded." },
  { id: "cts", label: "Completing the square", x: 880, y: 78, st: "untested", lad: [null, null, null, null, null, null], ev: "No evidence yet." },
  { id: "kin", label: "Kinematics", x: 770, y: 430, st: "fragile", lad: [1, 1, 0, null, null, null], ev: "Picks the right equation, confuses signs for downward motion." },
  { id: "proj", label: "Projectile motion", x: 925, y: 330, st: "untested", lad: [null, null, null, null, null, null], ev: "No evidence yet." },
];

export const EDGES: [string, string][] = [
  ["rat", "lin"], ["lin", "fac"], ["lin", "w2e"], ["lin", "sys"], ["sys", "w2e"], ["area", "w2e"], ["w2e", "qm"], ["fac", "qm"],
  ["fac", "qf"], ["qf", "qm"], ["area", "qm"], ["qm", "gp"], ["qf", "cts"], ["gp", "cts"], ["qm", "kin"], ["kin", "proj"], ["gp", "proj"],
];

export const RUNGS = ["Familiar problem", "Different numbers", "Words → equation", "New context", "Distractors added", "Combined with another concept"];

export const SIGNALS: [string, Strength, string][] = [
  ["Correctness", "untested", "No answer given yet, and none is needed at this stage."],
  ["Recognition", "fragile", "“I don’t see a quadratic.” The method family is not identified yet."],
  ["Representation", "weak", "No equation written. The words have not become algebra."],
  ["Concept", "strong", "Area is used correctly as the anchor quantity."],
  ["Procedure", "untested", "No algebra attempted yet."],
  ["Strategy", "fragile", "Started from the given number instead of naming the unknown."],
];

// [rung, what it means, before today, after today]
export const LADDER: [string, string, Strength, Strength][] = [
  ["Familiar", "Same structure, same form", "strong", "strong"],
  ["Surface variation", "New numbers and notation", "strong", "strong"],
  ["Representation switch", "Words → equation", "fragile", "verified"],
  ["Context switch", "Geometry → number puzzle", "untested", "verified"],
  ["Distractors", "Extra information, no trigger words", "untested", "untested"],
  ["Concept combination", "Quadratic plus another idea", "untested", "untested"],
];
