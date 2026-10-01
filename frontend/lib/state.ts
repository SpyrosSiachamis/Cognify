/* The whole app state in one place. A pure reducer, so it is easy to test and easy to explain. */

import type { BackendData } from "./backend";
import type { VerdictChanges } from "./api";

export type Theme = "velvet" | "salon";
export type View = "home" | "quick" | "session" | "result";
export type Mode = "simple" | "master";
export type TabId = "overview" | "reasoning" | "understanding" | "teaching";
export type LogKind = "" | "ok" | "ai";
export type LogEntry = { t: number; b: string; s: string; k: LogKind };
export type ToastState = { msg: string; label: string; tab: TabId } | null;

export const DEMO_PROBLEM =
  "A rectangle has an area of 48 m². Its length is 2 m greater than its width. Find its dimensions.";
export const DEMO_THOUGHT = "I know the area is 48, so length times width is 48. But I don’t see a quadratic here.";
// Seeded demo numbers shown in the top bar before anything is proven today.
export const BASE = { streak: 4, proven: 3 };

export type AppState = {
  theme: Theme;
  view: View;
  mode: Mode;
  problem: string;
  dim: boolean; // room dims during the fresh problem
  fresh: boolean; // something new in Progress
  verified: boolean; // transfer verified in this session
  bumped: boolean; // streak and proven chips already counted today's win
  shared: boolean; // student shared a first idea
  probed: boolean; // warm-up done
  thought: string;
  hints: number;
  log: LogEntry[];
  t0: number;
  run: number; // bumped for every new session so old async work stops
  sheetOpen: boolean;
  sheetRev: number; // counts openings, so the drawer replays its animations each time
  tab: TabId;
  mapSel: string;
  sealOpen: boolean;
  toast: ToastState;
  backend: BackendData | null; // what the backend knows about the learner; null = use the seeded history
  verdict: VerdictChanges | null; // the backend's before/after when it verified the fresh problem
};

export const initialState: AppState = {
  theme: "velvet",
  view: "home",
  mode: "master",
  problem: DEMO_PROBLEM,
  dim: false,
  fresh: false,
  verified: false,
  bumped: false,
  shared: false,
  probed: false,
  thought: "",
  hints: 0,
  log: [],
  t0: 0,
  run: 0,
  sheetOpen: false,
  sheetRev: 0,
  tab: "overview",
  mapSel: "qm",
  sealOpen: false,
  toast: null,
  backend: null,
  verdict: null,
};

export type Action =
  | { type: "theme"; theme: Theme }
  | { type: "view"; view: View }
  | { type: "mode"; mode: Mode }
  | { type: "problem"; problem: string }
  | { type: "dim"; on: boolean }
  | { type: "fresh"; on: boolean }
  | { type: "log"; b: string; s?: string; k?: LogKind; now: number }
  | { type: "hint" }
  | { type: "shared"; thought: string }
  | { type: "probed" }
  | { type: "verified" }
  | { type: "bump" }
  | { type: "sheet"; open: boolean; tab?: TabId }
  | { type: "tab"; tab: TabId }
  | { type: "mapSel"; id: string }
  | { type: "seal"; open: boolean }
  | { type: "toast"; toast: ToastState }
  | { type: "backend"; data: BackendData | null }
  | { type: "verdict"; changes: VerdictChanges }
  | { type: "startSession"; now: number }
  | { type: "newProblem" }
  | { type: "fullReset" };

export function reducer(s: AppState, a: Action): AppState {
  switch (a.type) {
    case "theme":
      return { ...s, theme: a.theme };
    case "view":
      return { ...s, view: a.view };
    case "mode":
      return { ...s, mode: a.mode };
    case "problem":
      return { ...s, problem: a.problem };
    case "dim":
      return { ...s, dim: a.on };
    case "fresh":
      return { ...s, fresh: a.on };
    case "log": {
      const t = Math.max(0, Math.round((a.now - s.t0) / 1000));
      return { ...s, log: [...s.log, { t, b: a.b, s: a.s ?? "", k: a.k ?? "" }] };
    }
    case "hint":
      return { ...s, hints: s.hints + 1 };
    case "shared":
      return { ...s, shared: true, thought: a.thought };
    case "probed":
      return { ...s, probed: true };
    case "verified":
      return { ...s, verified: true };
    case "bump":
      return { ...s, bumped: true };
    case "sheet":
      // Opening the drawer clears the "something new" dot and the toast.
      return a.open
        ? { ...s, sheetOpen: true, sheetRev: s.sheetRev + 1, tab: a.tab ?? s.tab, fresh: false, toast: null }
        : { ...s, sheetOpen: false };
    case "tab":
      return { ...s, tab: a.tab };
    case "mapSel":
      return { ...s, mapSel: a.id };
    case "seal":
      return { ...s, sealOpen: a.open };
    case "toast":
      return { ...s, toast: a.toast };
    case "backend":
      return { ...s, backend: a.data };
    case "verdict":
      return { ...s, verdict: a.changes };
    case "startSession":
      return {
        ...s,
        run: s.run + 1,
        shared: false,
        probed: false,
        thought: "",
        hints: 0,
        log: [],
        verdict: null,
        t0: a.now,
        dim: false,
        view: "session",
      };
    case "newProblem":
      return { ...s, run: s.run + 1, dim: false, sheetOpen: false, toast: null, problem: DEMO_PROBLEM, view: "home" };
    case "fullReset":
      return {
        ...initialState,
        theme: s.theme,
        backend: s.backend,
        run: s.run + 1,
      };
  }
}
