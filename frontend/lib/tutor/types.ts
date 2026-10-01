/* What the screens need from a tutor. The backend tutor (lib/tutor/backend.ts) implements it by mapping the
   backend's responses onto these turns; the screens never see raw API shapes except through these beats. */

import type { DiagnosisView, MethodView, Solution, Verdict } from "../api";
import type { Phase } from "../vocab";

// A tiny rich-text format so tutor text never needs raw HTML.
// A plain string is normal text, {b} is bold, {m} is inline math, {eq} is a displayed equation.
export type Seg = string | { b: string } | { m: string } | { eq: string };
export type Rich = Seg[];

export type TabName = "overview" | "reasoning" | "understanding" | "teaching";
export type LogKind = "" | "ok" | "ai";

// What the student is asked to do next. The backend has one turn endpoint, so every answer is free text.
export type Widget =
  | { kind: "reply"; kicker: string; placeholder: string; first: boolean } // first: the student's first idea
  | { kind: "stress"; kicker: string; problem: string; placeholder: string } // the fresh problem, no support
  | { kind: "ended"; message: string }; // the session is over without a verified result

// A tutor turn is a list of small beats the screen plays in order, then the next thing to ask.
export type Beat =
  | { say: Rich[] } // one tutor bubble: a list of paragraphs
  | { log: { b: string; s?: string; k?: LogKind } } // a line in the session activity log
  | { phase: Phase } // the backend's session phase
  | { diagnosis: DiagnosisView } // the reasoning step's reading of this answer
  | { method: MethodView } // the teaching move choose_strategy picked
  | { hints: number } // hints used so far, counted by the backend
  | { verdict: Verdict; over: boolean }
  | { fresh: true } // something new in Progress
  | { toast: { msg: string; label: string; tab: TabName } }
  | { dim: boolean } // dim the room for the fresh problem
  | { seal: true }; // VERIFIED

export type Turn = { beats: Beat[]; next: Widget | null }; // null: nothing more to ask

export type StudentInput = { text: string; first?: boolean };

export interface MasterSession {
  send(input: StudentInput, signal?: AbortSignal): Promise<Turn>;
  /** Leave the session: the backend returns the solution and records no evidence. */
  exit(): Promise<Solution>;
}

export interface TutorService {
  /** Start a Master session. The first turn opens the conversation. */
  begin(problem: string, signal?: AbortSignal): Promise<{ session: MasterSession; turn: Turn }>;
}
