import { describe, expect, it } from "vitest";
import { emptySession, initialState, reducer } from "@/lib/state";
import type { DiagnosisView } from "@/lib/api";

const DIAGNOSIS: DiagnosisView = { steps: [{ role: "compute", status: "correct", quote: "t = 2" }], main_gap: "recognition", alternatives: [], confidence: "medium" };

describe("app state", () => {
  it("starting a session clears the old one and shows the thread", () => {
    const old = { ...initialState, session: { ...emptySession, hintsUsed: 2, diagnosis: DIAGNOSIS }, log: [{ t: 1, b: "x", s: "", k: "" as const }], run: 3 };
    const next = reducer(old, { type: "startSession", now: 1000 });
    expect(next).toMatchObject({ session: emptySession, log: [], run: 4, view: "session", t0: 1000 });
  });

  it("log times are seconds since the session started", () => {
    let s = reducer(initialState, { type: "startSession", now: 10_000 });
    s = reducer(s, { type: "log", b: "Hello", now: 14_400 });
    expect(s.log[0]).toEqual({ t: 4, b: "Hello", s: "", k: "" });
  });

  it("a diagnosis is kept together with the student text it is about", () => {
    let s = reducer(initialState, { type: "sent", text: "my first idea", first: true });
    s = reducer(s, { type: "diagnosis", diagnosis: DIAGNOSIS });
    expect(s.session).toMatchObject({ firstIdea: "my first idea", diagnosis: DIAGNOSIS, diagnosedText: "my first idea" });
    s = reducer(s, { type: "sent", text: "second answer", first: false });
    expect(s.session.firstIdea).toBe("my first idea");
    expect(s.lastText).toBe("second answer");
  });

  it("opening Progress clears the news dot and the toast", () => {
    const s = reducer({ ...initialState, fresh: true, toast: { msg: "m", label: "l", tab: "reasoning" } }, { type: "sheet", open: true, tab: "teaching" });
    expect(s).toMatchObject({ sheetOpen: true, tab: "teaching", fresh: false, toast: null });
  });

  it("a new problem goes home with an empty box and keeps the learner views", () => {
    const views = { status: "error" as const, message: "down" };
    const s = reducer({ ...initialState, view: "result", problem: "other", views }, { type: "newProblem" });
    expect(s).toMatchObject({ view: "home", problem: "", views });
  });

  it("starting again after a lost session keeps the problem and clears the old session", () => {
    let s = reducer(initialState, { type: "problem", problem: "A ball is thrown up at 20 m/s." });
    s = reducer(s, { type: "startSession", now: 1 });
    s = reducer(s, { type: "sent", text: "my idea", first: true });
    const again = reducer(s, { type: "startSession", now: 2 });
    expect(again.problem).toBe("A ball is thrown up at 20 m/s.");
    expect(again.run).toBe(s.run + 1);
    expect(again.session.firstIdea).toBe("");
  });
});
