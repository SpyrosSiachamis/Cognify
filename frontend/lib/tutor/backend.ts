/* The real tutor: every turn is a call to the backend's Master session API, and every beat on screen is
   mapped from the backend's response. Nothing here decides anything; the backend owns the flow. */

import { api, isVerdictTurn, MARIA_ID, type AttemptResponse, type SessionStartResponse, type Solution, type TutorTurn, type VerdictTurn } from "../api";
import { gapLabel, modeLabel, strategyLabel } from "../vocab";
import { fromText } from "./rich";
import type { Beat, MasterSession, StudentInput, Turn, TutorService, Widget } from "./types";

// Why a safe fallback was sent, in the backend's own terms (reply_check.outcome). An unknown or missing outcome
// is reported as just a fallback: the screen never claims a cause the backend did not state.
const FALLBACK_CAUSE: Record<string, string> = {
  verifier_rejected: "Verifier rejected the reply",
  teaching_failed: "Teaching step failed",
  verifier_error: "Verifier could not check the draft",
  wrong_language: "Draft in the wrong language",
  turn_failed: "Turn failed",
};

const FIRST_IDEA: Widget = { kind: "reply", kicker: "Your first idea", placeholder: "Write your first idea, a plan, or an equation…", first: true };
const REPLY: Widget = { kind: "reply", kicker: "Your answer", placeholder: "Write your answer or your next step…", first: false };

/** POST /api/session → the opening turn. */
export function openingTurn(start: SessionStartResponse): Turn {
  return { beats: [{ phase: start.phase }, { hints: start.hints_used }, { say: fromText(start.message) }], next: FIRST_IDEA };
}

/** A teaching or stress-test turn (TutorTurn) → beats and the next question. */
function tutorTurn(turn: TutorTurn): Turn {
  const beats: Beat[] = [{ phase: turn.phase }, { hints: turn.hints_used }];
  if (turn.diagnosis) {
    const d = turn.diagnosis;
    beats.push({ diagnosis: d }, { fresh: true });
    beats.push({
      log: d.main_gap
        ? { b: "Read your reasoning", s: `Main gap: ${gapLabel(d.main_gap)} (confidence ${d.confidence})`, k: "ai" }
        : { b: "Read your reasoning", s: `No gap shown in this answer (confidence ${d.confidence})`, k: "ai" },
    });
  }
  if (turn.method) {
    const m = turn.method;
    beats.push({ method: m }, { log: { b: m.experiment ? "Teaching move · experiment" : "Teaching move", s: `${strategyLabel(m.name)} · ${modeLabel(m.mode)}`, k: "ai" } });
  }
  if (!turn.reply_check.approved) beats.push({ log: { b: FALLBACK_CAUSE[turn.reply_check.outcome ?? ""] ?? "Safe fallback sent", s: turn.reply_check.summary } });

  if (turn.phase === "stress_test" && turn.follow_up) {
    beats.push(
      { dim: true },
      { log: { b: "Support removed", s: "Fresh problem, no hints", k: "ai" } },
      { say: fromText(turn.message) },
    );
    return { beats, next: { kind: "stress", kicker: "Fresh problem · no hints", problem: turn.follow_up.problem, placeholder: "Show how you solve it…" } };
  }
  if (turn.diagnosis?.main_gap) beats.push({ toast: { msg: "Cognify read your reasoning", label: "See it", tab: "reasoning" } });
  beats.push({ say: fromText(turn.message) });
  return { beats, next: REPLY };
}

/** The verdict on the fresh problem (VerdictTurn). VERIFIED ends the session; a first NOT YET goes back to teaching. */
function verdictTurn(turn: VerdictTurn): Turn {
  const v = turn.verdict;
  const beats: Beat[] = [{ phase: "verdict" }, { verdict: v, over: turn.session_over }, { dim: false }, { fresh: true }];
  beats.push({ log: { b: v.result === "VERIFIED" ? "Verified" : "Not yet", s: v.evidence, k: v.result === "VERIFIED" ? "ok" : "" } });
  if (turn.message) beats.push({ say: fromText(turn.message) });
  if (v.result === "VERIFIED") {
    beats.push({ seal: true });
    return { beats, next: null };
  }
  if (turn.session_over) return { beats, next: { kind: "ended", message: v.evidence } };
  return { beats, next: REPLY }; // the backend moved the session back to teaching
}

export function mapAttempt(reply: AttemptResponse): Turn {
  return isVerdictTurn(reply) ? verdictTurn(reply) : tutorTurn(reply);
}

class BackendSession implements MasterSession {
  constructor(private readonly id: string) {}

  async send(input: StudentInput, signal?: AbortSignal): Promise<Turn> {
    return mapAttempt(await api.attempt(this.id, input.text, signal));
  }

  async exit(): Promise<Solution> {
    return (await api.exit(this.id)).solution;
  }
}

/** The tutor for the seeded demo learner (the backend's MARIA_ID). */
export const backendTutor: TutorService = {
  async begin(problem, signal) {
    const start = await api.startSession(problem, MARIA_ID, signal);
    return { session: new BackendSession(start.session_id), turn: openingTurn(start) };
  },
};
