import { describe, expect, it } from "vitest";
import { DEMO_PROBLEM, initialState, reducer } from "@/lib/state";

describe("app state", () => {
  it("starting a session clears the old one and shows the thread", () => {
    const old = { ...initialState, shared: true, hints: 2, log: [{ t: 1, b: "x", s: "", k: "" as const }], run: 3 };
    const next = reducer(old, { type: "startSession", now: 1000 });
    expect(next).toMatchObject({ shared: false, hints: 0, log: [], run: 4, view: "session", t0: 1000 });
  });

  it("log times are seconds since the session started", () => {
    let s = reducer(initialState, { type: "startSession", now: 10_000 });
    s = reducer(s, { type: "log", b: "Hello", now: 14_400 });
    expect(s.log[0]).toEqual({ t: 4, b: "Hello", s: "", k: "" });
  });

  it("opening Progress clears the news dot and the toast", () => {
    const s = reducer({ ...initialState, fresh: true, toast: { msg: "m", label: "l", tab: "reasoning" } }, { type: "sheet", open: true, tab: "teaching" });
    expect(s).toMatchObject({ sheetOpen: true, tab: "teaching", fresh: false, toast: null });
  });

  it("a new problem goes home and keeps what was proven", () => {
    const s = reducer({ ...initialState, view: "result", verified: true, problem: "other" }, { type: "newProblem" });
    expect(s).toMatchObject({ view: "home", verified: true, problem: DEMO_PROBLEM });
  });

  it("the demo reset forgets everything but the theme", () => {
    const s = reducer({ ...initialState, theme: "salon", verified: true, bumped: true }, { type: "fullReset" });
    expect(s).toMatchObject({ theme: "salon", verified: false, bumped: false });
  });
});
