/* What the screens need from a tutor. The scripted tutor implements this today;
   the real backend can replace it later without touching the screens. */

// A tiny rich-text format so tutor text never needs raw HTML.
// A plain string is normal text, {b} is bold, {m} is inline math, {eq} is a displayed equation.
export type Seg = string | { b: string } | { m: string } | { eq: string };
export type Rich = Seg[];

// Level 1 (Simple): a result and short steps. It writes nothing and is never evidence.
export type Answer = { result: Rich; steps: Rich[] };

export type TabName = "overview" | "reasoning" | "understanding" | "teaching";
export type LogKind = "" | "ok" | "ai";

// What the student is asked to do next.
export type Widget =
  | { kind: "idea"; placeholder: string; demo: string }
  | { kind: "probe"; kicker: string; prompt: Rich; placeholder: string; ariaLabel: string; demo: string }
  | {
      kind: "question";
      kicker: string;
      prompt: Rich;
      placeholder: string;
      ariaLabel: string;
      demo: string;
      hint: Rich;
      stage: 0 | 1; // which state of the rectangle diagram to start from
    }
  | { kind: "ready"; label: string }
  | { kind: "transfer"; kicker: string; problem: Rich; notYet: Rich; demoEquation: string; demoAnswer: string };

// A tutor turn is a list of small beats the screen plays in order, then the next thing to ask.
export type Beat =
  | { say: Rich[] } // one tutor bubble: a list of paragraphs
  | { log: { b: string; s?: string; k?: LogKind } } // a line in the session activity log
  | { mark: "shared"; thought: string }
  | { mark: "probed" }
  | { fresh: true } // something new in Progress
  | { toast: { msg: string; label: string; tab: TabName } }
  | { phase: 0 | 1 | 2 } // Think, Learn, Prove
  | { dim: boolean } // dim the room for the fresh problem
  | { built: { equation: string; summary: Rich } } // the "You built it" card
  | { pause: number }
  | { seal: true }; // transfer verified

export type Turn = {
  accepted: boolean; // false: stay on the same question
  feedback?: { tone: "good" | "nudge"; text: string };
  beats: Beat[];
  next: Widget | null; // null: nothing more to ask
};

// What the student sent. For the fresh problem, text is the equation and answer is the final number.
export type StudentInput = { text: string; answer?: string };

export interface MasterSession {
  send(input: StudentInput): Promise<Turn>;
}

export interface TutorService {
  /** Where the answer came from, so the UI can say so honestly. */
  readonly source: "scripted" | "backend";
  answer(problem: string): Promise<Answer>;
  /** Start a Master session. The first turn opens the conversation. */
  begin(problem: string): Promise<{ session: MasterSession; turn: Turn }>;
}
