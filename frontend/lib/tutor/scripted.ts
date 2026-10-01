/* The prepared scenario: the rectangle problem, with copy identical to the prototype. */

import { DEMO_THOUGHT } from "@/lib/state";
import type { Answer, MasterSession, StudentInput, Turn, TutorService, Widget } from "./types";

const RECTANGLE_ANSWER: Answer = {
  result: ["Dimensions: ", { b: "6 m × 8 m" }],
  steps: [
    ["Let the width be ", { m: "x" }, ". The length is ", { m: "x + 2" }, "."],
    ["Area gives ", { eq: "x(x + 2) = 48" }],
    ["Rearrange to ", { eq: "x² + 2x − 48 = 0" }],
    ["Factor ", { eq: "(x + 8)(x − 6) = 0" }, ", so ", { m: "x = 6" }, ". A width cannot be negative."],
  ],
};

const IDEA: Widget = { kind: "idea", placeholder: "Write your first idea, a plan, or an equation…", demo: DEMO_THOUGHT };

const PROBE: Widget = {
  kind: "probe",
  kicker: "Warm-up",
  prompt: ["Ana is 3 years older than Sam, and together their ages add up to 25. ", { b: "Write an equation." }],
  placeholder: "e.g.  s + … = 25",
  ariaLabel: "Your equation",
  demo: "x + (x + 3) = 25",
};

const Q1: Widget = {
  kind: "question",
  kicker: "Question 1 of 2",
  prompt: ["If the width is ", { m: "x" }, ", how would you write the length?"],
  placeholder: "length = …",
  ariaLabel: "Length in terms of x",
  demo: "x + 2",
  hint: ["Micro-hint: “2 m greater than the width.” Start from ", { m: "x" }, " and add."],
  stage: 0,
};

const Q2: Widget = {
  kind: "question",
  kicker: "Question 2 of 2",
  prompt: ["Area is length × width. What equation does that give you?"],
  placeholder: "… = 48",
  ariaLabel: "Area equation",
  demo: "x(x + 2) = 48",
  hint: ["Micro-hint: multiply the two sides you just named, then set it equal to the area."],
  stage: 1,
};

const READY: Widget = { kind: "ready", label: "I’m ready" };

const TRANSFER: Widget = {
  kind: "transfer",
  kicker: "Fresh problem · no hints · no explanations",
  problem: ["Two consecutive even numbers multiply to ", { b: "168" }, ". What is the smaller number?"],
  notYet: [
    { b: "Not yet." },
    " That number does not give 168 with the next even number. This is new evidence, not failure. If the first number is ",
    { m: "x" },
    ", what is the next even number?",
  ],
  demoEquation: "x(x + 2) = 168",
  demoAnswer: "12",
};

// Same normalisation as the prototype: ignore spaces, dots and stars, and a leading "length=".
const normalise = (s: string) => s.replace(/\s|·|\*/g, "").replace(/^(length=|l=)/, "").toLowerCase();

export const checkLength = (v: string) => /^(x\+2|2\+x)$/.test(normalise(v));
export const checkArea = (v: string) => {
  const n = normalise(v);
  return n.includes("48") && /x\(x\+2\)|\(x\+2\)x|x\(2\+x\)|x\^?2\+2x|x²\+2x/.test(n);
};
export const checkWarmUp = (eq: string) =>
  /2[a-z]\+3=25|[a-z]\+[a-z]\+3=25|[a-z]\+\([a-z]\+3\)=25|\([a-z]\+3\)\+[a-z]=25/.test(eq.replace(/\s/g, "").toLowerCase());
export const checkTransfer = (answer: string) => {
  const a = parseFloat((answer || "").replace(",", "."));
  return a === 12 || a === -14;
};

const opening: Turn = {
  accepted: true,
  beats: [{ say: [["Let’s take this one together."], ["Before I help, ", { b: "what would you try first?" }, " Even half an idea tells me a lot."]] }],
  next: IDEA,
};

/** One scripted session. It remembers which step the student is on. */
class ScriptedSession implements MasterSession {
  private step: "idea" | "probe" | "q1" | "q2" | "ready" | "transfer" | "done" = "idea";

  async send(input: StudentInput): Promise<Turn> {
    const text = input.text;
    switch (this.step) {
      case "idea": {
        this.step = "probe";
        const quote = text.slice(0, 70) + (text.length > 70 ? "…" : "");
        return {
          accepted: true,
          beats: [
            { mark: "shared", thought: text },
            { log: { b: "You shared your first idea", s: `“${quote}”` } },
            { say: [["Thanks, that helps. You ", { b: "anchored on the area" }, ", which is exactly the right instinct. The step from words to equation is where I want to look closer."]] },
            { fresh: true },
            { log: { b: "Read your reasoning", s: "Strong on concept, unsure on recognition", k: "ai" } },
            { say: [["One tiny warm-up, ten seconds, to see where the snag really is:"]] },
          ],
          next: PROBE,
        };
      }
      case "probe": {
        this.step = "q1";
        const good = checkWarmUp(text);
        return {
          accepted: true,
          beats: [
            { mark: "probed" },
            { log: { b: "Found the gap", s: "Turning words into an equation", k: "ai" } },
            { fresh: true },
            {
              say: [
                good
                  ? ["Clean. Your algebra is solid, so that is ", { b: "not" }, " the problem. The snag is smaller: turning “2 m greater” into the side of a rectangle."]
                  : ["Close. A quantity went missing from the equation, which tells me the gap is ", { b: "turning words into algebra" }, ", not the algebra itself."],
              ],
            },
            { toast: { msg: "Cognify found where you get stuck", label: "See it", tab: "reasoning" } },
            { say: [["So here is the plan: ", { b: "you" }, " build the equation, one small question at a time. I will only nudge."]] },
            { phase: 1 },
          ],
          next: Q1,
        };
      }
      case "q1": {
        if (!text.trim()) return { accepted: false, feedback: { tone: "nudge", text: "Type an expression using x." }, beats: [], next: Q1 };
        if (!checkLength(text)) return { accepted: false, feedback: { tone: "nudge", text: "Close. Read it again: the length is 2 m greater than the width." }, beats: [], next: Q1 };
        this.step = "q2";
        return {
          accepted: true,
          feedback: { tone: "good", text: "Yes. The length is two more than the width." },
          beats: [{ log: { b: "Built the length", s: "x + 2", k: "ok" } }, { say: [["Exactly. Now put the two sides together."]] }],
          next: Q2,
        };
      }
      case "q2": {
        if (!text.trim()) return { accepted: false, feedback: { tone: "nudge", text: "Write an equation with x and 48." }, beats: [], next: Q2 };
        if (!checkArea(text)) return { accepted: false, feedback: { tone: "nudge", text: "Almost. Multiply length by width and set it equal to 48." }, beats: [], next: Q2 };
        this.step = "ready";
        return {
          accepted: true,
          feedback: { tone: "good", text: "That’s the model. You wrote it yourself." },
          beats: [
            { log: { b: "Wrote the model", s: "x(x + 2) = 48", k: "ok" } },
            { fresh: true },
            { pause: 500 },
            { built: { equation: "x(x + 2) = 48", summary: ["x² + 2x − 48 = 0 → (x + 8)(x − 6) = 0 → width ", { b: "6 m" }, ", length ", { b: "8 m" }, "."] } },
            { say: [["Now the part I care about most. ", { b: "I take the help away" }, " and give you a brand-new problem. If you can do it alone, it is really yours."]] },
          ],
          next: READY,
        };
      }
      case "ready": {
        this.step = "transfer";
        return {
          accepted: true,
          beats: [{ phase: 2 }, { dim: true }, { log: { b: "Support removed", s: "Fresh problem, no hints", k: "ai" } }],
          next: TRANSFER,
        };
      }
      case "transfer": {
        if (!checkTransfer(input.answer ?? "")) return { accepted: false, beats: [], next: TRANSFER };
        this.step = "done";
        return { accepted: true, beats: [{ seal: true }], next: null };
      }
      default:
        return { accepted: false, beats: [], next: null };
    }
  }
}

export const scriptedTutor: TutorService = {
  source: "scripted",
  async answer() {
    return RECTANGLE_ANSWER;
  },
  async begin() {
    return { session: new ScriptedSession(), turn: opening };
  },
};
