/* Saving a live session as a replay. The recorder watches the live tutor (lib/tutor/backend.ts) and keeps each backend
   response exactly as it arrived, with what the student sent and how long it took. buildRecording turns that into a
   Recording (lib/tutor/replay.ts), the same shape as the hand-written replays: when the backend's development trace is
   on, its events become the "Trace · …" backstage lines; when it is off, the replay simply has none. Saved replays live
   in this browser's storage, and can be downloaded and imported as a .json file to present on another machine. */

import { api, checks, MARIA_ID, type AttemptResponse, type DiagnosisView, type SessionStartResponse, type Solution, type TraceEventView } from "../api";
import type { Views } from "../backend";
import { gapLabel, roleLabel, strategyLabel } from "../vocab";
import { liveTutor } from "./backend";
import { readToast, reading, trace, type Recording } from "./replay";
import type { Beat, TutorService } from "./types";

type RecordedStep = { student: string; response: AttemptResponse; ms: number };

/** A live session as it was recorded so far. */
export type Draft = {
  problem: string;
  start: SessionStartResponse;
  setUpMs: number;
  steps: RecordedStep[];
  solution: Solution | null; // set only if the student pressed Exit
  startedAt: string;
  viewsBefore: Views | null;
};

/** A live tutor that records every session it runs. getViews reads the learner views as they stand at the start. */
export function createRecorder(getViews: () => Views | null): { tutor: TutorService; current: () => Draft | null } {
  let draft: Draft | null = null;
  const tutor = liveTutor({
    started(problem, start, ms) {
      draft = { problem, start, setUpMs: ms, steps: [], solution: null, startedAt: new Date().toISOString(), viewsBefore: getViews() };
    },
    answered(text, response, ms) {
      if (draft && response.session_id === draft.start.session_id) draft.steps.push({ student: text, response, ms });
    },
    exited(solution) {
      if (draft) draft.solution = solution;
    },
  });
  return { tutor, current: () => draft };
}

// ---- the trace, read defensively: development data, so any field may be missing ----

type Payload = Record<string, unknown>;
const str = (p: Payload, k: string): string | null => (typeof p[k] === "string" ? (p[k] as string) : null);
const num = (p: Payload, k: string): number | null => (typeof p[k] === "number" ? (p[k] as number) : null);
const obj = (p: Payload, k: string): Payload | null => (typeof p[k] === "object" && p[k] !== null && !Array.isArray(p[k]) ? (p[k] as Payload) : null);
const list = (p: Payload, k: string): unknown[] => (Array.isArray(p[k]) ? (p[k] as unknown[]) : []);
const secs = (ms: number) => `${(ms / 1000).toFixed(1)} s`;
const values = (p: Payload) => list(p, "demonstrated_values").filter((v): v is number => typeof v === "number").map((v) => String(v)).join(", ");

type QuotedStep = { role: string; status: string; quote: string | null };
const steps = (p: Payload | null): QuotedStep[] =>
  (p ? list(p, "steps") : []).flatMap((s) =>
    typeof s === "object" && s !== null && typeof (s as Payload).role === "string" && typeof (s as Payload).status === "string"
      ? [{ role: (s as Payload).role as string, status: (s as Payload).status as string, quote: typeof (s as Payload).quote === "string" ? ((s as Payload).quote as string) : null }]
      : [],
  );

/** The backstage lines for one service call's events (one answer, or the session start). */
function backstage(events: TraceEventView[], step: RecordedStep | null): Beat[] {
  const beats: Beat[] = [];
  const timings: Record<string, number> = {};
  let proposal: Payload | null = null;
  let toast = false;
  for (const { event_type: type, payload: p } of events) {
    if (type === "MODEL_CALL") {
      const op = str(p, "operation");
      if (op) timings[op] = (timings[op] ?? 0) + (num(p, "latency_ms") ?? 0);
    } else if (type === "SESSION_STARTED") {
      beats.push(trace("hidden solution written", "The set-up model solved the problem first. Kept on the backend, never shown."));
      if (str(p, "concept_name")) beats.push(trace("concept", `${str(p, "concept_name")} · ${str(p, "concept_state") ?? "untested"} for this learner`));
    } else if (type === "REASONING_READ") {
      proposal = obj(p, "proposal");
    } else if (type === "DIAGNOSIS_RESULT") {
      const final = obj(p, "diagnosis");
      // Claims the model proposed that code did not accept as the student's own evidence.
      const kept = new Set(steps(final).map((s) => `${s.role}|${s.quote}`));
      const dropped = steps(proposal).filter((s) => s.status !== "missing" && s.quote && !kept.has(`${s.role}|${s.quote}`));
      if (dropped.length)
        beats.push(trace("claim dropped", `${dropped.map((s) => `${roleLabel(s.role)} (“${s.quote}”)`).join("; ")}: not accepted as the student's own evidence. No quote, no claim.`));
      const gap = str(p, "main_gap");
      const gapStep = obj(p, "gap_step");
      if (gap && str(p, "mode") === "teach")
        beats.push(trace("gap located", `${gapLabel(gap)}${gapStep && str(gapStep, "role") ? ` at ${roleLabel(str(gapStep, "role")!)}` : ""} (confidence ${str(p, "confidence") ?? "?"}).`));
      if (str(p, "method") && str(p, "strategy_reason"))
        beats.push(trace("method chosen by code", `choose_strategy · ${str(p, "decision_mode") ?? ""}: ${str(p, "strategy_reason")} Recorded.`));
      if (p.gap_repaired === true && str(p, "repair_reason")) beats.push(trace("gap repaired", str(p, "repair_reason")!));
      const state = str(p, "resolution_state");
      if (state === "CURRENT_TARGET_RESOLVED") beats.push(trace("step demonstrated", `Code checked the work. Demonstrated so far: ${values(p) || "none"}.`));
      if (state === "PROBLEM_RESOLVED") beats.push(trace("problem resolved", `Every step holds (demonstrated: ${values(p)}). Solved with help is not verified yet.`));
      // The live turn that moves on to the fresh problem does not send its reading; the trace has it.
      if (final && step && step.response.phase === "stress_test" && checksDiagnosis(final)) {
        const { steps: read, main_gap, alternatives, confidence } = final;
        beats.unshift(...reading({ steps: read, main_gap, alternatives, confidence }));
        toast = true;
      }
    } else if (type === "VERIFIER_RESULT") {
      const outcome = str(p, "outcome");
      if (outcome === "approved") beats.push(trace("reply checked", `Approved: ${str(p, "note") ?? ""}`));
      else if (outcome) beats.push(trace("reply rejected", `${str(p, "reason") ?? outcome}: ${str(p, "note") ?? ""} Rewritten with that reason.`, ""));
    } else if (type === "TEACHING_FALLBACK") {
      beats.push(trace("safe fallback", `No draft passed after ${num(p, "attempts") ?? "?"} tries, so an explained fallback was sent instead.`, ""));
    } else if (type === "REPLY_SENT" && p.counts_as_hint === true) {
      beats.push(trace("hint counted", "A teaching move counts as one hint: it decides later whether a correct answer is independent."));
    } else if (type === "FOLLOW_UP_RESULT") {
      const outcome = str(p, "outcome");
      if (outcome === "approved") beats.push(trace("fresh problem approved", str(p, "note") ?? ""));
      else if (outcome) beats.push(trace("fresh problem rejected", `${str(p, "note") ?? outcome} Never shown.`, ""));
    } else if (type === "TRANSFER_RESULT") {
      const yes = (k: string) => (p[k] === true ? "yes" : "no");
      const verified = p.verified === true;
      beats.push(trace("judge's evidence", `Correct: ${yes("correct")} · own work: ${yes("own_work")} · reasoning: ${str(p, "reasoning_quality") ?? "?"}. ${str(p, "judge_note") ?? ""}`));
      beats.push(
        trace("code decides", `verified = correct AND independent (own work: ${yes("own_work")}, ${num(p, "hints_used") ?? 0} hint(s), at most 2) → ${verified ? "VERIFIED" : "NOT YET"}. The model never says VERIFIED.`),
      );
      const method = str(p, "method_credited");
      if (method)
        beats.push(
          trace(
            "method credited",
            `${strategyLabel(method)} for ${gapLabel(str(p, "gap_credited") ?? "")} gaps: ${num(p, "strategy_independent_successes_before")} / ${num(p, "strategy_uses_before")} → ${num(p, "strategy_independent_successes_after")} / ${num(p, "strategy_uses_after")} (independent / uses).`,
            "ok",
          ),
        );
    }
  }
  const spent = Object.entries(timings).map(([op, ms]) => `${op.replace(/_/g, " ")} ${secs(ms)}`);
  if (spent.length) beats.push(trace("timing", spent.join(" · ")));
  // A reading with no gap gets no toast live; the replay offers it, so the audience can open each reading.
  const r = step?.response;
  if (toast || (r && "diagnosis" in r && r.diagnosis && !r.diagnosis.main_gap)) beats.push(readToast);
  return beats;
}

function checksDiagnosis(d: Payload): d is Payload & DiagnosisView {
  return Array.isArray(d.steps) && Array.isArray(d.alternatives) && typeof d.confidence === "string" && (d.main_gap === null || typeof d.main_gap === "string");
}

/** The backstage lines for the start and for each recorded answer. Events are grouped by the service call (turn) that
    produced them; an answer finds its call by the text the trace recorded, so a failed call that was retried does not
    shift the rest. */
export function traceBackstage(events: TraceEventView[], recorded: RecordedStep[]): { setUp: Beat[]; steps: Beat[][] } {
  const byTurn = new Map<number, TraceEventView[]>();
  for (const e of [...events].sort((a, b) => a.sequence - b.sequence)) byTurn.set(e.turn, [...(byTurn.get(e.turn) ?? []), e]);
  const turns = [...byTurn.keys()].sort((a, b) => a - b);
  const used = new Set<number>([0]);
  const textOf = (turn: number) => {
    const e = byTurn.get(turn)?.find((x) => x.event_type === "STUDENT_RESPONSE");
    return e ? str(e.payload, "text") : null;
  };
  return {
    setUp: backstage(byTurn.get(0) ?? [], null),
    steps: recorded.map((step) => {
      const turn = turns.find((t) => !used.has(t) && textOf(t) === step.student && byTurn.get(t)?.some((e) => e.event_type !== "STUDENT_RESPONSE"));
      if (turn === undefined) return [];
      used.add(turn);
      return backstage(byTurn.get(turn) ?? [], step);
    }),
  };
}

// ---- building and keeping a recording ----

const emptyViews: Views = {
  learner: { student_id: MARIA_ID, display_name: "Maria", is_seeded: true, concepts: [] },
  strategies: { student_id: MARIA_ID, display_name: "Maria", is_seeded: true, rows: [], methods: [] },
};

/** The recorded session as a replay. Reads the trace when the backend has it (DEBUG_TRACE); never fails without it. */
export async function buildRecording(draft: Draft, viewsAfter: Views | null): Promise<Recording> {
  const id = draft.start.session_id;
  let events: TraceEventView[] = [];
  try {
    events = (await api.debugTrace(id)).events;
  } catch {
    // Tracing is off or the backend cannot answer: the replay is saved without backstage lines.
  }
  const lines = events.length ? traceBackstage(events, draft.steps) : { setUp: [], steps: draft.steps.map(() => []) };
  const date = new Date(draft.startedAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const before = draft.viewsBefore ?? viewsAfter ?? emptyViews;
  return {
    id: `saved-${id.slice(0, 8)}`,
    title: draft.problem.length > 70 ? `${draft.problem.slice(0, 67)}…` : draft.problem,
    problem: draft.problem,
    label: `Replay of recorded session ${id.slice(0, 8)} (${date}). Every reply is what Cognify sent live; no backend or model is called.`,
    setUpMs: draft.setUpMs,
    setUp: lines.setUp,
    start: draft.start,
    steps: draft.steps.map((s, i) => ({ ...s, backstage: lines.steps[i] ?? [] })),
    solution: draft.solution ?? { result: "The solution was not shown in the recorded session.", steps: [] },
    views: { before, after: viewsAfter ?? before },
  };
}

/** Whether a value (a file, the browser's storage) is a recording this app can play: every response must pass the
    same checks as a live one. */
export function isRecording(v: unknown): v is Recording {
  if (typeof v !== "object" || v === null) return false;
  const r = v as Partial<Recording>;
  return (
    typeof r.id === "string" && typeof r.title === "string" && typeof r.problem === "string" && typeof r.label === "string" &&
    typeof r.setUpMs === "number" && Array.isArray(r.setUp) && checks.start(r.start) && Array.isArray(r.steps) && r.steps.length > 0 &&
    r.steps.every((s) => typeof s?.student === "string" && typeof s.ms === "number" && Array.isArray(s.backstage) && checks.attempt(s.response)) &&
    typeof r.solution === "object" && r.solution !== null && typeof r.views === "object" && r.views !== null &&
    typeof r.views.before === "object" && typeof r.views.after === "object"
  );
}

const SAVED_KEY = "cognify-replays";

// The browser's storage, read as an external store: one cached list per stored value, so React sees a stable snapshot.
let cache: { raw: string | null; list: Recording[] } | null = null;
const listeners = new Set<() => void>();

function readRaw(): string | null {
  try {
    return localStorage.getItem(SAVED_KEY);
  } catch {
    return null; // storage missing or blocked: no saved replays
  }
}

function parse(raw: string | null): Recording[] {
  try {
    const list = JSON.parse(raw ?? "[]");
    return Array.isArray(list) ? list.filter(isRecording) : [];
  } catch {
    return [];
  }
}

/** Replays saved in this browser (the same array until the stored value changes). */
export function listSaved(): Recording[] {
  const raw = readRaw();
  if (!cache || cache.raw !== raw) cache = { raw, list: parse(raw) };
  return cache.list;
}

export const findSaved = (id: string): Recording | null => listSaved().find((r) => r.id === id) ?? null;

/** For useSyncExternalStore: saves in this tab, and in other tabs (the storage event). */
export function subscribeSaved(listener: () => void): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key === SAVED_KEY) listener();
  };
  listeners.add(listener);
  addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    removeEventListener("storage", onStorage);
  };
}

function write(list: Recording[]): boolean {
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify(list));
  } catch {
    return false;
  } finally {
    listeners.forEach((l) => l());
  }
  return true;
}

/** Save (or replace, by id) a replay in this browser. False when the browser will not store it. */
export const saveRecording = (recording: Recording): boolean => write([recording, ...listSaved().filter((r) => r.id !== recording.id)]);

export const removeSaved = (id: string): void => void write(listSaved().filter((r) => r.id !== id));

/** Offer the replay as a .json file, to import on another machine. */
export function downloadRecording(recording: Recording): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(recording, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: `cognify-replay-${recording.id}.json` });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Read a downloaded replay file. Throws when it is not one. */
export async function readRecordingFile(file: File): Promise<Recording> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    throw new Error("That file is not JSON.");
  }
  if (!isRecording(parsed)) throw new Error("That file is not a Cognify replay.");
  return parsed;
}
