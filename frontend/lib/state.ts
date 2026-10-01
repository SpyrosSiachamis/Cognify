/* The whole app state in one place. A pure reducer, so it is easy to test and easy to explain.
   Everything about the learner and the session is a copy of what the backend returned; the backend stays
   authoritative and nothing here is computed in its place. */

import type { Views } from "./backend";
import type { DiagnosisView, MethodView, Verdict } from "./api";
import type { Phase } from "./vocab";

export type Theme = "velvet" | "salon";
export type View = "home" | "session" | "result";
export type TabId = "overview" | "reasoning" | "understanding" | "teaching";
export type LogKind = "" | "ok" | "ai";
export type LogEntry = { t: number; b: string; s: string; k: LogKind };
export type ToastState = { msg: string; label: string; tab: TabId } | null;

// An example the student can load into the box ("Try an example"). It is input, never a response.
export const EXAMPLE_PROBLEM =
  "A rectangle has an area of 48 m². Its length is 2 m greater than its width. Find its dimensions.";

/** The learner views from the backend: still loading, loaded, or failed (with the reason). */
export type ViewsState = { status: "loading" } | { status: "ok"; data: Views } | { status: "error"; message: string };

/** The current Master session, as the backend reported it. */
export type SessionState = {
  phase: Phase | null;
  hintsUsed: number;
  firstIdea: string; // the student's first message, which the first diagnosis reads
  diagnosis: DiagnosisView | null; // the latest diagnosis the backend returned
  diagnosedText: string; // the student text that diagnosis is about
  method: MethodView | null; // the latest teaching move
  verdict: Verdict | null;
  over: boolean;
};

export const emptySession: SessionState = {
  phase: null,
  hintsUsed: 0,
  firstIdea: "",
  diagnosis: null,
  diagnosedText: "",
  method: null,
  verdict: null,
  over: false,
};

export type AppState = {
  theme: Theme;
  view: View;
  problem: string;
  dim: boolean; // room dims during the fresh problem
  fresh: boolean; // something new in Progress
  views: ViewsState;
  session: SessionState;
  lastText: string; // the student's latest message (the one the next backend reply is about)
  log: LogEntry[];
  t0: number;
  run: number; // bumped for every new session so old async work stops
  sheetOpen: boolean;
  sheetRev: number; // counts openings, so the drawer replays its animations each time
  tab: TabId;
  mapSel: string;
  sealOpen: boolean;
  toast: ToastState;
};

export const initialState: AppState = {
  theme: "velvet",
  view: "home",
  problem: "",
  dim: false,
  fresh: false,
  views: { status: "loading" },
  session: emptySession,
  lastText: "",
  log: [],
  t0: 0,
  run: 0,
  sheetOpen: false,
  sheetRev: 0,
  tab: "overview",
  mapSel: "",
  sealOpen: false,
  toast: null,
};

export type Action =
  | { type: "theme"; theme: Theme }
  | { type: "view"; view: View }
  | { type: "problem"; problem: string }
  | { type: "dim"; on: boolean }
  | { type: "fresh"; on: boolean }
  | { type: "log"; b: string; s?: string; k?: LogKind; now: number }
  | { type: "views"; views: ViewsState }
  | { type: "sent"; text: string; first: boolean }
  | { type: "phase"; phase: Phase }
  | { type: "hints"; hints: number }
  | { type: "diagnosis"; diagnosis: DiagnosisView }
  | { type: "method"; method: MethodView }
  | { type: "verdict"; verdict: Verdict; over: boolean }
  | { type: "sheet"; open: boolean; tab?: TabId }
  | { type: "tab"; tab: TabId }
  | { type: "mapSel"; id: string }
  | { type: "seal"; open: boolean }
  | { type: "toast"; toast: ToastState }
  | { type: "startSession"; now: number }
  | { type: "newProblem" };

const patch = (s: AppState, session: Partial<SessionState>): AppState => ({ ...s, session: { ...s.session, ...session } });

export function reducer(s: AppState, a: Action): AppState {
  switch (a.type) {
    case "theme":
      return { ...s, theme: a.theme };
    case "view":
      return { ...s, view: a.view };
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
    case "views":
      return { ...s, views: a.views };
    case "sent":
      return { ...(a.first ? patch(s, { firstIdea: a.text }) : s), lastText: a.text };
    case "phase":
      return patch(s, { phase: a.phase });
    case "hints":
      return patch(s, { hintsUsed: a.hints });
    case "diagnosis":
      return patch(s, { diagnosis: a.diagnosis, diagnosedText: s.lastText });
    case "method":
      return patch(s, { method: a.method });
    case "verdict":
      return patch(s, { verdict: a.verdict, over: a.over });
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
    case "startSession":
      return { ...s, run: s.run + 1, session: emptySession, lastText: "", log: [], t0: a.now, dim: false, view: "session" };
    case "newProblem":
      return { ...s, run: s.run + 1, dim: false, sheetOpen: false, sealOpen: false, toast: null, problem: "", view: "home" };
  }
}
