import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionTraceView } from "../lib/api";
import { buildRecording, createRecorder, findSaved, isRecording, listSaved, removeSaved, saveRecording, traceBackstage } from "../lib/tutor/recorder";
import { RECORDINGS, replay, type Recording } from "../lib/tutor/replay";
import type { Beat } from "../lib/tutor/types";

// The school session (acac5a33) as the backend traced it, and as its responses arrived (the hand-written replay).
const TRACE: SessionTraceView = JSON.parse(readFileSync(join(__dirname, "fixtures/school_trace.json"), "utf8"));
const SCHOOL = RECORDINGS.school;
const lines = (beats: Beat[]) => beats.flatMap((b) => ("log" in b ? [`${b.log.b} | ${b.log.s}`] : []));

describe("trace → backstage lines", () => {
  const { setUp, steps } = traceBackstage(TRACE.events, SCHOOL.steps);

  it("covers the start and every answer, matched to the right call", () => {
    expect(steps).toHaveLength(SCHOOL.steps.length);
    expect(lines(setUp).join("\n")).toMatch(/hidden solution written[\s\S]*concept \| Percentage calculations · untested/);
    expect(lines(setUp).join("\n")).not.toContain("76.5"); // the hidden answer is never written into a replay
  });

  it("explains the teaching move: the gap, the method code chose, the check, the hint", () => {
    const first = lines(steps[0]).join("\n");
    expect(first).toContain("gap located | Procedure");
    expect(first).toContain("method chosen by code | choose_strategy · cold_start: No history yet for procedure gaps");
    expect(first).toContain("reply checked | Approved");
    expect(first).toContain("hint counted");
    expect(first).toContain("claim dropped | Identify quantities (“A school has 600 students. 15% are absent on Monday.”)");
  });

  it("restores the reading the live turn did not send, and the fresh problem's checks", () => {
    const toFresh = steps[3];
    expect("diagnosis" in toFresh[0]).toBe(true); // the third answer's reading, first
    const text = lines(toFresh).join("\n");
    expect(text).toContain("problem resolved");
    expect(text).toMatch(/fresh problem rejected \| .*380\.8 books.* Never shown\./);
    expect(text).toContain("fresh problem approved");
    expect(toFresh.some((b) => "toast" in b)).toBe(true);
  });

  it("states the verdict as code decided it, and the method credited", () => {
    const text = lines(steps[4]).join("\n");
    expect(text).toContain("judge's evidence | Correct: yes · own work: yes · reasoning: strong");
    expect(text).toContain("→ VERIFIED. The model never says VERIFIED.");
    expect(text).toContain("method credited | Worked example for Procedure gaps: 0 / 0 → 1 / 1");
  });
});

describe("recording a live session and saving it as a replay", () => {
  const store = new Map<string, string>();
  beforeEach(() => {
    store.clear();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  /** Play the school session against a fake backend that answers exactly as the live one did. */
  async function record(trace: SessionTraceView | null): Promise<Recording> {
    let answer = 0;
    vi.stubGlobal("fetch", async (url: string) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url.endsWith("/api/session")) return json(SCHOOL.start);
      if (url.endsWith("/attempt")) return json(SCHOOL.steps[answer++].response);
      if (url.endsWith("/debug-trace")) return trace ? json(trace) : json({ error: { code: "not_found", message: "Not Found", retryable: false } }, 404);
      return json({}, 404);
    });
    const recorder = createRecorder(() => SCHOOL.views.before);
    const { session } = await recorder.tutor.begin(SCHOOL.problem);
    for (const step of SCHOOL.steps) await session.send({ text: step.student });
    return buildRecording(recorder.current()!, SCHOOL.views.after);
  }

  it("keeps every response as it arrived, with the trace's backstage lines", async () => {
    const recording = await record(TRACE);
    expect(isRecording(recording)).toBe(true);
    expect(recording.id).toBe("saved-acac5a33");
    expect(recording.steps.map((s) => s.response)).toEqual(SCHOOL.steps.map((s) => s.response));
    expect(recording.steps.map((s) => s.student)).toEqual(SCHOOL.steps.map((s) => s.student));
    expect(recording.views).toEqual(SCHOOL.views);
    expect(lines(recording.steps[4].backstage).join("\n")).toContain("→ VERIFIED");
  });

  it("saves, finds, replays to VERIFIED and removes", async () => {
    const recording = await record(TRACE);
    expect(saveRecording(recording)).toBe(true);
    expect(findSaved(recording.id)).toEqual(recording);
    expect(saveRecording(recording)).toBe(true); // saving again replaces, by id
    expect(listSaved()).toHaveLength(1);

    vi.useFakeTimers();
    const { tutor } = replay(findSaved(recording.id)!);
    const opening = tutor.begin(recording.problem);
    await vi.runAllTimersAsync();
    const { session } = await opening;
    let last: Beat[] = [];
    for (const step of recording.steps) {
      const sent = session.send({ text: step.student });
      await vi.runAllTimersAsync();
      last = (await sent).beats;
    }
    expect(last.some((b) => "seal" in b)).toBe(true);

    removeSaved(recording.id);
    expect(listSaved()).toEqual([]);
  });

  it("still saves a playable replay when tracing is off, just without backstage lines", async () => {
    const recording = await record(null);
    expect(isRecording(recording)).toBe(true);
    expect(recording.setUp).toEqual([]);
    expect(recording.steps.every((s) => s.backstage.length === 0)).toBe(true);
  });

  it("never loads a file or stored value that is not a playable replay", () => {
    const tampered = structuredClone(SCHOOL) as unknown as { steps: { response: Record<string, unknown> }[] };
    delete tampered.steps[0].response.reply_check;
    expect(isRecording(SCHOOL)).toBe(true);
    expect(isRecording(tampered)).toBe(false);
    expect(isRecording({ id: "x" })).toBe(false);
    store.set("cognify-replays", JSON.stringify([tampered, SCHOOL]));
    expect(listSaved().map((r) => r.id)).toEqual(["school"]);
    store.set("cognify-replays", "not json");
    expect(listSaved()).toEqual([]);
  });
});
