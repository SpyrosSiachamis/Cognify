/* What the screens need from a tutor. The scripted tutor implements this today;
   the real backend can replace it later without touching the screens. */

// A tiny rich-text format so tutor text never needs raw HTML.
// A plain string is normal text, {b} is bold, {m} is inline math, {eq} is a displayed equation.
export type Seg = string | { b: string } | { m: string } | { eq: string };
export type Rich = Seg[];

// Level 1 (Simple): a result and short steps. It writes nothing and is never evidence.
export type Answer = { result: Rich; steps: Rich[] };

export interface TutorService {
  /** Where the answer came from, so the UI can say so honestly. */
  readonly source: "scripted" | "backend";
  answer(problem: string): Promise<Answer>;
}
