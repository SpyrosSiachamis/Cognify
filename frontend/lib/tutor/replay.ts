/* Replays of recorded Master sessions, for presenting: the screens play each one exactly as it played live, with no
   backend and no model. Every response below is what the backend returned in that session (2 Oct 2026, the demo
   learner, Mistral Large 3 on Bedrock), rebuilt from its development trace, and the mapping onto beats is the real one
   (lib/tutor/backend.ts). The only additions: backstage lines from the same trace ("Trace · …") in the activity log;
   the last answer's reading (the trace has it, but the live turn went straight to the fresh problem and did not send
   it); and the "Cognify read your reasoning" toast after readings that named no gap (live, it shows only for a gap),
   so the audience can open each reading. The student's answers are pre-filled: press Enter to send each one. */

import type { AttemptResponse, DiagnosisView, LearnerConcept, SessionStartResponse, Solution, StrategyRow, TutorTurn } from "../api";
import type { Views } from "../backend";
import { mapAttempt, openingTurn } from "./backend";
import type { Beat, LogKind, MasterSession, StudentInput, Turn, TutorService, Widget } from "./types";

type Step = {
  student: string; // what the student sent (pre-filled in the answer box)
  response: AttemptResponse; // what the backend answered
  ms: number; // how long the backend took for this turn (its model calls in the trace)
  backstage: Beat[]; // from the trace, played just before the tutor's message
};

export type Recording = {
  id: string;
  title: string;
  problem: string;
  label: string;
  note?: string; // a known issue the session shows, stated on the replay list
  setUpMs: number;
  setUp: Beat[];
  start: SessionStartResponse;
  steps: Step[];
  solution: Solution; // shown only if the presenter presses Exit
  views: { before: Views; after: Views };
};

const MARIA = "16e82ef2-adee-4671-8393-c6b50ac91672";
const FIRST_THOUGHT = "Before I help, what would you try first? Even an incomplete idea is useful.";
const FRESH = "Now I am removing the support. New problem, same underlying idea, different surface.";

export const trace = (b: string, s: string, k: LogKind = "ai"): Beat => ({ log: { b: `Trace · ${b}`, s, k } });
export const readToast: Beat = { toast: { msg: "Cognify read your reasoning", label: "See it", tab: "reasoning" } };
/** A reading the live turn computed but did not send (it went straight to the fresh problem). */
export const reading = (d: DiagnosisView): Beat[] => [
  { diagnosis: d },
  { fresh: true },
  { log: { b: "Read your reasoning", s: `No gap shown in this answer (confidence ${d.confidence})`, k: "ai" } },
];
/** A known issue, said plainly at the moment the session shows it. */
const knownIssue = (s: string): Beat => ({ log: { b: "Known issue · whole items are not rounded", s, k: "" } });
const approved = (summary: string): TutorTurn["reply_check"] => ({ approved: true, outcome: "approved", summary });

// ---- the demo learner over the day: seeded history first, then each session's own result ----

const kinematics: LearnerConcept = {
  concept_id: "44d54897-9ec4-45b9-8da1-d4ea95697d1d",
  name: "Constant-acceleration kinematics",
  state: "fragile",
  evidence: ["Seeded demo history: recognition gap in 3 earlier sessions."],
};
const division: LearnerConcept = {
  concept_id: "634e70e1-a88f-4ec9-a22e-2715b53a6ca6",
  name: "Division of whole numbers",
  state: "verified",
  evidence: ["Student explicitly shows the subtraction (45 - 5 = 40) and the division (40 ÷ 8 = 5), matching the rubric's steps."],
};
// Fragile before the rectangle session: from an earlier session today whose NOT YET came from a wrong generated
// answer key (the bug the expected-solution check addresses). Its evidence line is that bug's text, so it is left out.
const quadraticsBefore: LearnerConcept = { concept_id: "32853770-e986-4c9a-a2f3-5a0dd948b93e", name: "Quadratic equations", state: "fragile", evidence: [] };
const quadraticsAfter: LearnerConcept = {
  ...quadraticsBefore,
  state: "verified",
  evidence: ["The student explicitly defines the height as h, expresses the base as h + 4, and sets up the area equation (1/2)(h + 4)(h) = 30."],
};

const rows = (visual: [number, number]): StrategyRow[] => [
  { gap: "recognition", method: "socratic", uses: 5, independent_successes: 3, experiments: 0 },
  { gap: "recognition", method: "visual_decomposition", uses: visual[0], independent_successes: visual[1], experiments: 0 },
  { gap: "recognition", method: "worked_example", uses: 7, independent_successes: 4, experiments: 0 },
];
const views = (concepts: LearnerConcept[], strategyRows: StrategyRow[]): Views => ({
  learner: { student_id: MARIA, display_name: "Maria", is_seeded: true, concepts },
  strategies: {
    student_id: MARIA,
    display_name: "Maria",
    is_seeded: true,
    rows: strategyRows,
    methods: strategyRows.map(({ method, uses, independent_successes }) => ({ method, uses, independent_successes })),
  },
});

// ---- session 66149ef0: books on shelves (arithmetic, no gap, no hints) ----

const BOOKS_ID = "66149ef0-e71c-4d85-9ba9-1aeafe5f6aee";
const BOOKS_PROBLEM =
  "A box contains 36 books. 12 are removed. The remaining books are divided equally among 6 shelves. How many books are on each shelf?";

const books: Recording = {
  id: "books",
  title: "Books on shelves",
  problem: BOOKS_PROBLEM,
  label: "Replay of recorded session 66149ef0 (2 Oct 2026). Every reply is what Cognify sent live; no backend or model is called.",
  setUpMs: 4264,
  setUp: [
    trace("hidden solution written", "The set-up model solved the problem first. The result stays on the backend, never shown. 4.3 s"),
    trace("concept", "Division of whole numbers · untested for this learner"),
  ],
  start: { session_id: BOOKS_ID, phase: "ask_first_thought", message: FIRST_THOUGHT, hints_used: 0 },
  steps: [
    {
      student: "I would first subtract the 12 removed books from 36, then divide the remaining books equally among 6 shelves.",
      ms: 8541 + 1118 + 1226,
      response: {
        session_id: BOOKS_ID,
        phase: "teach",
        message:
          "Great start! You’ve identified the right steps: first subtract the 12 books, then divide the remaining books equally. What number would you get after subtracting the 12 books from 36?",
        diagnosis: {
          steps: [
            { role: "choose_method", status: "correct", quote: "subtract the 12 removed books from 36" },
            { role: "set_up", status: "correct", quote: "subtract the 12 removed books from 36, then divide the remaining books equally among 6 shelves" },
          ],
          main_gap: null,
          alternatives: [],
          confidence: "medium",
        },
        method: null,
        hints_used: 0,
        reply_check: approved("The reply is a probe question that builds on the student's correct thinking without giving hints or leaking the answer."),
      },
      backstage: [
        trace("claim dropped", "The model credited “identify quantities” with a quote from the problem, not from the student. No quote, no claim."),
        trace("no gap invented", "Substitute, compute and interpret are not done yet, but nothing is wrong, so there is nothing to teach. Mode: probe."),
        trace("reply checked", "Approved before sending: asks about the student's own thinking, no hint, answer withheld (“4 books”). 8.5 s read · 1.1 s draft · 1.2 s check"),
        readToast,
      ],
    },
    {
      student: "36 - 12 = 24 books",
      ms: 1501 + 547 + 611,
      response: {
        session_id: BOOKS_ID,
        phase: "teach",
        message: "Nice work! You’ve found that there are 24 books left. Now, how could you divide these 24 books equally among the 6 shelves?",
        diagnosis: {
          steps: [
            { role: "identify_quantities", status: "correct", quote: "36 books" },
            { role: "set_up", status: "correct", quote: "36 - 12" },
            { role: "substitute", status: "correct", quote: "36 - 12" },
            { role: "compute", status: "correct", quote: "36 - 12 = 24" },
          ],
          main_gap: null,
          alternatives: [],
          confidence: "high",
        },
        method: null,
        hints_used: 0,
        reply_check: approved("The reply is a probe question that builds on the student's correct step without providing new information or hints."),
      },
      backstage: [
        trace("answer to the question asked", "Read as an answer to the tutor's question, so steps it did not ask about are not counted as missing."),
        trace("arithmetic checked by code", "36 − 12 = 24 holds. Demonstrated: 24. Current target resolved; next target: the division (hidden)."),
        trace("claim dropped", "“Choose method: correct” came with no quote. No quote, no claim, even for praise."),
        trace("reply checked", "Approved: builds on the correct step, adds nothing new. 1.5 s read · 0.5 s draft · 0.6 s check"),
        readToast,
      ],
    },
    {
      student: "24/6 = 4 books per shelve",
      ms: 2239 + 24925 + 853 + 2620 + 1063,
      response: {
        session_id: BOOKS_ID,
        phase: "stress_test",
        message: FRESH,
        follow_up: {
          problem: "A baker has 45 cupcakes to pack into boxes. She uses 5 cupcakes to decorate the shop display. The rest are packed equally into 8 boxes. How many cupcakes are in each box?",
        },
        hints_used: 0,
        reply_check: approved("The follow-up problem effectively tests the same principle in a new context without leaking answers or hints."),
      },
      backstage: [
        ...reading({
          steps: [
            { role: "identify_quantities", status: "correct", quote: "24" },
            { role: "set_up", status: "correct", quote: "24/6" },
            { role: "compute", status: "correct", quote: "24/6 = 4" },
            { role: "interpret", status: "correct", quote: "4 books per shelve" },
          ],
          main_gap: null,
          alternatives: [],
          confidence: "high",
        }),
        trace("problem resolved", "24, then 4, demonstrated with every calculation true. Solved with help is not verified yet."),
        trace("fresh problem 1 rejected", "Checker: 48 − 10 = 38 does not divide by 5, and its own answer key contradicted itself. Never shown. 24.9 s write · 0.9 s check", ""),
        trace("fresh problem 2 approved", "Same idea (remove, then share equally), new context, tests the set-up step. 2.6 s write · 1.1 s check"),
        readToast,
      ],
    },
    {
      student: "45-5 = 40 cupcakes remaining. Afterwards we do 40/8 = 5 cupcakes. So every box will have 5 cupcakes",
      ms: 973,
      response: {
        session_id: BOOKS_ID,
        phase: "verdict",
        session_over: true,
        message: "You solved it on your own.",
        verdict: {
          result: "VERIFIED",
          evidence: division.evidence[0],
          independent: true,
          remaining_gap: null,
          changes: { concept: { concept_id: division.concept_id, name: division.name, before: "untested", after: "verified" }, strategy: null },
        },
      },
      backstage: [
        trace("judge's evidence", "Correct: yes · own work: yes (shows the set-up step) · reasoning: strong. 1.0 s"),
        trace("code decides", "verified = correct AND independent (own work, 0 hints ≤ 2) → VERIFIED. The model never says VERIFIED."),
      ],
    },
  ],
  solution: { result: "4 books", steps: ["36 − 12 = 24 books remain.", "24 ÷ 6 = 4 books per shelf."] },
  views: { before: views([kinematics], rows([9, 7])), after: views([kinematics, division], rows([9, 7])) },
};

// ---- session 61e0ec69: the rectangle (a quadratic; a recognition gap, a chosen method, one hint) ----

const RECT_ID = "61e0ec69-10af-40df-abd6-0e82fcf853bc";
const RECT_PROBLEM = "A rectangle has an area of 48 m². Its length is 2 m greater than its width. Find its dimensions.";
const RECT_WORK =
  "I can factor the quadratic:\n\nw² + 2w - 48 = 0\n\nI need two numbers that multiply to -48 and add to 2. Those numbers are 8 and -6.\n\nSo:\n\n(w + 8)(w - 6) = 0\n\nTherefore:\n\nw + 8 = 0 → w = -8\n\nor\n\nw - 6 = 0 → w = 6\n\nSince a width cannot be negative, w = 6.\n\nThe length is w + 2, so:\n\nlength = 6 + 2 = 8\n\nTherefore, the dimensions are 6 m × 8 m.";
const TRIANGLE_WORK =
  "Let the height be h. Since the base is 4 meters longer, the base is h + 4.\n\nThe area of a triangle is 1/2 × base × height, so:\n\n1/2 h(h + 4) = 30\n\nMultiply both sides by 2:\n\nh(h + 4) = 60\n\nExpand:\n\nh² + 4h = 60\n\nMove everything to one side:\n\nh² + 4h - 60 = 0\n\nFactor:\n\n(h + 10)(h - 6) = 0\n\nSo:\n\nh + 10 = 0 → h = -10\n\nor\n\nh - 6 = 0 → h = 6\n\nA length cannot be negative, so h = 6.\n\nThe base is:\n\n6 + 4 = 10\n\nTherefore, the height is 6 m and the base is 10 m.";

const rectangle: Recording = {
  id: "rectangle",
  title: "The rectangle (a quadratic)",
  problem: RECT_PROBLEM,
  label: "Replay of recorded session 61e0ec69 (2 Oct 2026). Every reply is what Cognify sent live; no backend or model is called.",
  setUpMs: 1820,
  setUp: [
    trace("hidden solution written", "The set-up model solved the problem first: width 6 m, length 8 m. Kept on the backend, never shown. 1.8 s"),
    trace("concept", "Quadratic equations · fragile for this learner (from an earlier session)"),
  ],
  start: { session_id: RECT_ID, phase: "ask_first_thought", message: FIRST_THOUGHT, hints_used: 0 },
  steps: [
    {
      student: "Perhaps let w as width, length = w+2",
      ms: 25981 + 905 + 709,
      response: {
        session_id: RECT_ID,
        phase: "teach",
        message:
          "You’ve set width as w and length as w + 2—great start! Let’s draw this rectangle: label the width as w and the length as w + 2. Where does the area of 48 m² fit into this picture?",
        diagnosis: {
          steps: [
            { role: "identify_quantities", status: "correct", quote: "let w as width, length = w+2" },
            { role: "choose_method", status: "missing", quote: null },
            { role: "set_up", status: "missing", quote: null },
            { role: "substitute", status: "missing", quote: null },
            { role: "compute", status: "missing", quote: null },
            { role: "interpret", status: "missing", quote: null },
          ],
          main_gap: "recognition",
          alternatives: [{ gap: "strategy_choice", confidence: "low" }],
          confidence: "high",
        },
        method: { name: "visual_decomposition", mode: "best_known", experiment: false, reason: "Worked 7 of 9 times for you on recognition gaps." },
        hints_used: 0,
        reply_check: approved(
          "The reply sets up a visual structure (a labelled rectangle) and asks the student to place the area in it, fulfilling the visual_decomposition method and targeting the recognition gap.",
        ),
      },
      backstage: [
        trace("gap located", "The quantities are right (quoted). The step that is missing is choosing the relation that links them to the area: a recognition gap. Alternative: strategy choice (low)."),
        trace("method chosen by code", "choose_strategy · best known for this learner: visual decomposition worked 7 of 9 times on recognition gaps. Recorded."),
        trace("reply checked", "Approved: a labelled picture and one question, aimed at the gap; answer withheld (“Width = 6 m, length = 8 m”). 26.0 s read · 0.9 s draft · 0.7 s check"),
        trace("hint counted", "A teaching move counts as one hint: it decides later whether a correct answer is independent."),
      ],
    },
    {
      student: "The area is length × width, so w(w + 2) = 48.",
      ms: 2032 + 1190 + 596,
      response: {
        session_id: RECT_ID,
        phase: "teach",
        message: "You’ve written the equation w(w + 2) = 48 clearly. What do you think the next step could be to find the value of w?",
        diagnosis: {
          steps: [
            { role: "identify_quantities", status: "correct", quote: "The area is length × width, so w(w + 2) = 48." },
            { role: "choose_method", status: "correct", quote: "The area is length × width, so w(w + 2) = 48." },
            { role: "set_up", status: "correct", quote: "w(w + 2) = 48." },
          ],
          main_gap: null,
          alternatives: [],
          confidence: "high",
        },
        method: null,
        hints_used: 1,
        reply_check: approved("The reply is a probe question that asks about the student's own thinking without providing hints, facts, or steps about the problem."),
      },
      backstage: [
        trace("gap repaired", "Code compared the gap step with last turn: choose method was missing, now it is correct, in the student's own words: “The area is length × width”."),
        trace("next step only", "Nothing left to teach at this step, so Cognify asks about the next one (mode: probe). No method, no hint."),
        trace("reply checked", "Approved: asks about the student's own thinking. 2.0 s read · 1.2 s draft · 0.6 s check"),
        readToast,
      ],
    },
    {
      student: "Expanding gives w² + 2w = 48, so w² + 2w - 48 = 0",
      ms: 1689 + 561 + 1867,
      response: {
        session_id: RECT_ID,
        phase: "teach",
        message: "Great job expanding the equation! Now that you have w² + 2w - 48 = 0, how do you think you could solve for w?",
        diagnosis: {
          steps: [{ role: "compute", status: "correct", quote: "Expanding gives w² + 2w = 48, so w² + 2w - 48 = 0" }],
          main_gap: null,
          alternatives: [],
          confidence: "high",
        },
        method: null,
        hints_used: 1,
        reply_check: approved("The reply is a probe question that asks about the student's own thinking without providing hints or explanations about the problem."),
      },
      backstage: [
        trace("claim dropped", "The model also credited set-up with “w(w + 2) = 48”. That is the previous answer, not this one. No quote, no claim."),
        trace("reply checked", "Approved. 1.7 s read · 0.6 s draft · 1.9 s check"),
        readToast,
      ],
    },
    {
      student: RECT_WORK,
      ms: 2238 + 1226 + 14571,
      response: {
        session_id: RECT_ID,
        phase: "stress_test",
        message: FRESH,
        follow_up: {
          problem: "A triangular garden has an area of 30 m². The base of the triangle is 4 meters longer than its height. Find the lengths of the base and the height of the garden.",
        },
        hints_used: 1,
        reply_check: approved("The follow-up problem successfully changes the context while preserving the concept invariant and targeting the set_up step."),
      },
      backstage: [
        ...reading({
          steps: [
            { role: "set_up", status: "correct", quote: "w² + 2w - 48 = 0" },
            { role: "choose_method", status: "correct", quote: "I need two numbers that multiply to -48 and add to 2." },
            { role: "compute", status: "correct", quote: "Those numbers are 8 and -6." },
            { role: "set_up", status: "correct", quote: "(w + 8)(w - 6) = 0" },
            { role: "compute", status: "correct", quote: "w + 8 = 0 → w = -8\n\nor\n\nw - 6 = 0 → w = 6" },
            { role: "interpret", status: "correct", quote: "Since a width cannot be negative, w = 6.\n\nThe length is w + 2, so:\n\nlength = 6 + 2 = 8\n\nTherefore, the dimensions are 6 m × 8 m." },
          ],
          main_gap: null,
          alternatives: [],
          confidence: "high",
        }),
        trace("roots checked by code", "w = 6 and w = −8 both satisfy w² + 2w − 48 = 0 and the earlier w(w + 2) = 48; 6 + 2 = 8. Demonstrated: 6, 8. The negative root is rejected in the student's words."),
        trace("problem resolved", "Every step holds, with one hint along the way. Solved with help is not verified yet."),
        trace("fresh problem approved", "A triangle instead of a rectangle: same idea (name, relate, set up a quadratic), tests the set-up step. 1.2 s write · 14.6 s check"),
        readToast,
      ],
    },
    {
      student: TRIANGLE_WORK,
      ms: 598,
      response: {
        session_id: RECT_ID,
        phase: "verdict",
        session_over: true,
        message: "You solved it on your own.",
        verdict: {
          result: "VERIFIED",
          evidence: quadraticsAfter.evidence[0],
          independent: true,
          remaining_gap: null,
          changes: {
            concept: { concept_id: quadraticsBefore.concept_id, name: quadraticsBefore.name, before: "fragile", after: "verified" },
            strategy: {
              gap: "recognition",
              method: "visual_decomposition",
              before: { uses: 9, independent_successes: 7 },
              after: { uses: 10, independent_successes: 8 },
            },
          },
        },
      },
      backstage: [
        trace("judge's evidence", "Correct: yes (h = 6 m, base 10 m) · own work: yes (sets up (1/2)(h + 4)(h) = 30 itself) · reasoning: strong. 0.6 s"),
        trace("code decides", "verified = correct AND independent (own work, 1 hint ≤ 2) → VERIFIED. The model never says VERIFIED."),
        trace("method credited", "Visual decomposition for recognition gaps: 9 uses / 7 independent successes → 10 / 8. Next time this gap shows, that evidence ranks the methods.", "ok"),
      ],
    },
  ],
  solution: { result: "Width = 6 m, length = 8 m", steps: ["w(w + 2) = 48", "w² + 2w − 48 = 0", "(w + 8)(w − 6) = 0", "w = 6 (a width is positive), length = 8"] },
  views: {
    before: views([kinematics, division, quadraticsBefore], rows([9, 7])),
    after: views([kinematics, division, quadraticsAfter], rows([10, 8])),
  },
};

// ---- session acac5a33: school percentages (three chained percentages; shows the fractional-items known issue) ----

const SCHOOL_ID = "acac5a33-889b-4294-84ba-094eea7e0cd2";
const SCHOOL_PROBLEM =
  "A school has 600 students. 15% are absent on Monday. Of the students who are present, 40% participate in a sports event. Of the remaining present students, 25% participate in a music activity.";
const WHOLE_ITEMS =
  "Cognify does not round or reject fractional counts of whole items, so “76.5 students” and “100.8 books” pass as answers. " +
  "Easily fixable (a whole-number check on counted quantities in the set-up and fresh-problem checks), but not prioritised because of the hackathon deadline.";
const LIBRARY_WORK =
  "I’d first calculate how many books are lost during the year. 10% of 800 = 0.10 × 800 = 80 books lost.\n\nThat leaves 800 − 80 = 720 books remaining.\n\nNext, I’d calculate how many of those 720 books are placed on the special display. 30% of 720 = 0.30 × 720 = 216 books on display.\n\nSo there are 720 − 216 = 504 books that are not on display.\n\nFinally, I’d calculate 20% of those 504 books for repair. 0.20 × 504 = 100.8 books.\n\nThat gives 504 − 100.8 = 403.2 books not chosen for repair.";

const percentagesVerified: LearnerConcept = {
  concept_id: "2a19acaa-fddd-4be1-903d-9d6d05e651de",
  name: "Percentage calculations",
  state: "verified",
  evidence: [
    "The student explicitly carries out each sequential percentage calculation on the updated quantity (e.g., '30% of 720', '20% of 504') and arrives at the final result of 100.8 books for repair.",
  ],
};
const workedExampleForProcedure = (uses: number): StrategyRow => ({ gap: "procedure", method: "worked_example", uses, independent_successes: uses, experiments: 0 });

const school: Recording = {
  id: "school",
  title: "School percentages (three steps)",
  problem: SCHOOL_PROBLEM,
  label: "Replay of recorded session acac5a33 (2 Oct 2026). Every reply is what Cognify sent live; no backend or model is called.",
  note: `Known issue: ${WHOLE_ITEMS}`,
  setUpMs: 1006,
  setUp: [
    trace("hidden solution written", "The set-up model solved the problem first: “76.5 students” in the music activity. Kept on the backend, never shown. 1.0 s"),
    knownIssue(WHOLE_ITEMS),
    trace("concept", "Percentage calculations · untested for this learner"),
  ],
  start: { session_id: SCHOOL_ID, phase: "ask_first_thought", message: FIRST_THOUGHT, hints_used: 0 },
  steps: [
    {
      student: "I would first calculate how many students are absent on Monday.",
      ms: 2026 + 997 + 807,
      response: {
        session_id: SCHOOL_ID,
        phase: "teach",
        message:
          "Let’s look at a similar problem to practice the next step:\n*A library has 400 books. 10% are checked out on Tuesday. Of the books still in the library, 30% are placed on display. How many books are still in the library after the 10% are checked out?*\n\nYou’d calculate: 10% of 400 = 0.10 × 400 = 40 books checked out, then 400 – 40 = 360 books still in the library.\n\nHow would you adapt this to find the number of present students in your problem?",
        diagnosis: {
          steps: [
            { role: "choose_method", status: "correct", quote: "I would first calculate how many students are absent on Monday." },
            { role: "set_up", status: "missing", quote: null },
            { role: "substitute", status: "missing", quote: null },
            { role: "compute", status: "missing", quote: null },
            { role: "interpret", status: "missing", quote: null },
          ],
          main_gap: "procedure",
          alternatives: [
            { gap: "representation", confidence: "low" },
            { gap: "strategy_choice", confidence: "medium" },
          ],
          confidence: "medium",
        },
        method: { name: "worked_example", mode: "cold_start", experiment: false, reason: "No history yet for procedure gaps, so starting with worked example." },
        hints_used: 0,
        reply_check: approved(
          "The reply provides a worked example of a different problem, leaving the student to adapt the reasoning to their own problem, which fully aligns with the worked_example method.",
        ),
      },
      backstage: [
        trace("claim dropped", "The model credited “identify quantities” with the problem's own sentence (“A school has 600 students. 15% are absent on Monday.”). No quote, no claim."),
        trace("gap located", "A plan with no working yet: the first calculation is the step not done. Gap: procedure (medium). Alternatives: strategy choice (medium), representation (low)."),
        trace("method chosen by code", "choose_strategy · cold start: no history yet for this learner's procedure gaps, so a worked example. Recorded."),
        trace("reply checked", "Approved: a worked example of a different problem (a library), so the student still does their own. Answer withheld. 2.0 s read · 1.0 s draft · 0.8 s check"),
        trace("hint counted", "A teaching move counts as one hint: it decides later whether a correct answer is independent."),
      ],
    },
    {
      student: "So I’d first find 15% of the 600 students: 0.15 × 600 = 90 students absent. Then I’d subtract those 90 from the total: 600 − 90 = 510 students present.",
      ms: 2363 + 652 + 720,
      response: {
        session_id: SCHOOL_ID,
        phase: "teach",
        message: "Great job calculating the number of present students! Now, how would you find out how many of these 510 students participate in the sports event?",
        diagnosis: {
          steps: [
            { role: "identify_quantities", status: "correct", quote: "15% of the 600 students" },
            { role: "choose_method", status: "correct", quote: "find 15% of the 600 students" },
            { role: "substitute", status: "correct", quote: "0.15 × 600" },
            { role: "compute", status: "correct", quote: "0.15 × 600 = 90 students absent" },
            { role: "set_up", status: "correct", quote: "subtract those 90 from the total: 600 − 90" },
            { role: "compute", status: "correct", quote: "600 − 90 = 510 students present" },
          ],
          main_gap: null,
          alternatives: [],
          confidence: "high",
        },
        method: null,
        hints_used: 1,
        reply_check: approved("The reply is a probe question focused on the student's next step, with no hint, leak, or heavy hint."),
      },
      backstage: [
        trace("gap repaired", "The worked example transferred: the student's own correct work demonstrates the step, with no wrong step."),
        trace("arithmetic checked by code", "0.15 × 600 = 90 and 600 − 90 = 510 hold. Demonstrated: 90, 510. Next target: 40% of 510 (hidden)."),
        trace("reply checked", "Approved: asks about the next step only. 2.4 s read · 0.7 s draft · 0.7 s check"),
        readToast,
      ],
    },
    {
      student: "I’d find 40% of the 510 students who are present. So, 0.40 × 510 = 204 students participate in the sports event.",
      ms: 2589 + 720 + 706,
      response: {
        session_id: SCHOOL_ID,
        phase: "teach",
        message: "Great! You’ve correctly found how many students participate in the sports event. What would you do next with the remaining present students?",
        diagnosis: {
          steps: [
            { role: "identify_quantities", status: "correct", quote: "the 510 students who are present" },
            { role: "choose_method", status: "correct", quote: "find 40% of the 510 students" },
            { role: "set_up", status: "correct", quote: "0.40 × 510" },
            { role: "compute", status: "correct", quote: "0.40 × 510 = 204" },
            { role: "interpret", status: "correct", quote: "204 students participate in the sports event" },
          ],
          main_gap: null,
          alternatives: [],
          confidence: "high",
        },
        method: null,
        hints_used: 1,
        reply_check: approved("The reply is a probe question that builds on the student's correct step without giving away the next step or leaking the answer."),
      },
      backstage: [
        trace("arithmetic checked by code", "0.40 × 510 = 204 holds, applied to the present students (not the 600). Demonstrated: 204. Next target: 510 − 204 = 306 (hidden)."),
        trace("reply checked", "Approved. 2.6 s read · 0.7 s draft · 0.7 s check"),
        readToast,
      ],
    },
    {
      student:
        "I’d subtract the 204 students in the sports event from the 510 present students, giving 306 students remaining. Then I’d calculate 25% of those 306 students: 0.25 × 306 = 76.5, so 76.5 students would participate in the music activity. That leaves 306 − 76.5 = 229.5 students who participate in neither activity.",
      ms: 2280 + 2183 + 844 + 1671 + 566,
      response: {
        session_id: SCHOOL_ID,
        phase: "stress_test",
        message: FRESH,
        follow_up: {
          problem: "A library has 800 books. During a year, 10% of the books are lost. Of the remaining books, 30% are placed on a special display. From the books not on display, 20% are chosen for repair.",
        },
        hints_used: 1,
        reply_check: approved("The follow-up problem successfully changes the context while preserving the concept invariant and target step."),
      },
      backstage: [
        ...reading({
          steps: [
            { role: "identify_quantities", status: "correct", quote: "the 204 students in the sports event from the 510 present students, giving 306 students remaining" },
            { role: "choose_method", status: "correct", quote: "calculate 25% of those 306 students" },
            { role: "compute", status: "correct", quote: "0.25 × 306 = 76.5" },
            {
              role: "interpret",
              status: "correct",
              quote: "so 76.5 students would participate in the music activity. That leaves 306 − 76.5 = 229.5 students who participate in neither activity.",
            },
          ],
          main_gap: null,
          alternatives: [],
          confidence: "high",
        }),
        trace("problem resolved", "Every calculation holds: 306, 76.5, 229.5 demonstrated. Solved with one hint along the way, so not verified yet."),
        knownIssue("“76.5 students” and “229.5 students” were accepted: the arithmetic is true, but a count of students should be whole. Fixable with a whole-number check; not prioritised for the deadline."),
        trace("fresh problem 1 rejected", "Checker: its answer was 380.8 books, “change the numbers to ensure whole-number results”. Never shown. 2.2 s write · 0.8 s check", ""),
        trace("fresh problem 2 approved", "Same idea (each percentage of the updated amount), new context (a library), tests the set-up step. 1.7 s write · 0.6 s check"),
        knownIssue("The approved fresh problem's own answer is 100.8 books: the checker caught fractional books once and missed them here. A code check would make this consistent."),
        readToast,
      ],
    },
    {
      student: LIBRARY_WORK,
      ms: 5049,
      response: {
        session_id: SCHOOL_ID,
        phase: "verdict",
        session_over: true,
        message: "You solved it on your own.",
        verdict: {
          result: "VERIFIED",
          evidence: percentagesVerified.evidence[0],
          independent: true,
          remaining_gap: null,
          changes: {
            concept: { concept_id: percentagesVerified.concept_id, name: percentagesVerified.name, before: "untested", after: "verified" },
            strategy: { gap: "procedure", method: "worked_example", before: { uses: 0, independent_successes: 0 }, after: { uses: 1, independent_successes: 1 } },
          },
        },
      },
      backstage: [
        trace("judge's evidence", "Correct: yes (100.8 books, matching the rubric) · own work: yes (each percentage on the updated amount: “30% of 720”, “20% of 504”) · reasoning: strong. 5.0 s"),
        trace("code decides", "verified = correct AND independent (own work, 1 hint ≤ 2) → VERIFIED. The model never says VERIFIED."),
        trace("method credited", "Worked example for procedure gaps: 0 uses → 1 use, 1 independent success. The first observed evidence for this learner's procedure gaps.", "ok"),
        knownIssue("The verdict rests on the right method; “100.8 books” as a count is the same rounding gap, not the student's error."),
      ],
    },
  ],
  solution: {
    result: "76.5 students",
    steps: ["15% of 600 = 90 absent; 600 − 90 = 510 present.", "40% of 510 = 204 in sports; 510 − 204 = 306 remain.", "25% of 306 = 76.5 in music."],
  },
  views: {
    before: views([kinematics, division, quadraticsAfter], rows([10, 8])),
    after: views([kinematics, division, quadraticsAfter, percentagesVerified], [workedExampleForProcedure(1), ...rows([10, 8])]),
  },
};

export const RECORDINGS: Record<string, Recording> = { books, rectangle, school };

// ---- playing a recording through the real screens ----

/** The backstage lines go in just before the tutor speaks (or the room dims), after the screen's own beats. */
function withBackstage(turn: Turn, backstage: Beat[]): Turn {
  const at = turn.beats.findIndex((b) => "say" in b || "dim" in b);
  const beats = at < 0 ? [...turn.beats, ...backstage] : [...turn.beats.slice(0, at), ...backstage, ...turn.beats.slice(at)];
  return { ...turn, beats };
}

/** The next answer box, pre-filled with what the student sent live. */
function prefilled(next: Widget | null, text: string | undefined): Widget | null {
  if (!next || next.kind === "ended" || text === undefined) return next;
  return { ...next, prefill: text };
}

// Long model calls are shortened for the room; the trace lines still show the real timings.
const pause = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, Math.min(Math.max(ms, 900), 2600));
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("cancelled", "AbortError"));
    });
  });

/** A tutor that replays one recording, and the learner views as they stood before and after its verdict. */
export function replay(recording: Recording): { tutor: TutorService; loadViews: () => Promise<Views> } {
  let verdictPlayed = false;

  class ReplaySession implements MasterSession {
    private i = 0;

    async send(_input: StudentInput, signal?: AbortSignal): Promise<Turn> {
      const step = recording.steps[Math.min(this.i, recording.steps.length - 1)];
      await pause(step.ms, signal);
      this.i += 1;
      if (step.response.phase === "verdict") verdictPlayed = true;
      const turn = withBackstage(mapAttempt(step.response), step.backstage);
      return { ...turn, next: prefilled(turn.next, recording.steps[this.i]?.student) };
    }

    async exit(): Promise<Solution> {
      return recording.solution;
    }
  }

  return {
    tutor: {
      async begin(_problem, signal) {
        verdictPlayed = false;
        await pause(recording.setUpMs, signal);
        const turn = withBackstage(openingTurn(recording.start), recording.setUp);
        return { session: new ReplaySession(), turn: { ...turn, next: prefilled(turn.next, recording.steps[0].student) } };
      },
    },
    loadViews: async () => (verdictPlayed ? recording.views.after : recording.views.before),
  };
}
