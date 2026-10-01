import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, checks, type StrategyView, type TutorTurn, type VerdictTurn } from "@/lib/api";
import { loadViews, provenConcepts, strategyGroups } from "@/lib/backend";
import { backendTutor, mapAttempt } from "@/lib/tutor/backend";
import { fromText } from "@/lib/tutor/rich";

afterEach(() => vi.unstubAllGlobals());

// Response bodies shaped like the backend's (copied from the Pydantic contract examples).
const START = { session_id: "s1", phase: "ask_first_thought", message: "Before I help, what would you try first?", hints_used: 0 };
const TEACH: TutorTurn = {
  session_id: "s1",
  phase: "teach",
  message: "You found the time. What does **2.04 s** tell you?",
  diagnosis: {
    steps: [
      { role: "compute", status: "correct", quote: "t = 2.04 s" },
      { role: "choose_method", status: "missing", quote: null },
    ],
    main_gap: "recognition",
    alternatives: [{ gap: "representation", confidence: "low" }],
    confidence: "medium",
  },
  method: { name: "visual_decomposition", mode: "experiment", experiment: true, reason: "Testing another method." },
  hints_used: 1,
  reply_check: { approved: true, summary: "No answer given." },
};
const STRESS: TutorTurn = {
  session_id: "s1",
  phase: "stress_test",
  message: "Now I am removing the support.",
  follow_up: { problem: "A stone is launched upward at 15 m/s." },
  hints_used: 1,
  reply_check: { approved: true, summary: "Follow-up keeps the principle." },
};
const verdict = (result: "VERIFIED" | "NOT YET", over: boolean): VerdictTurn => ({
  session_id: "s1",
  phase: "verdict",
  session_over: over,
  message: result === "VERIFIED" ? "You solved it on your own." : "Not yet.",
  verdict: {
    result,
    evidence: "Chose the equation that needs no time.",
    independent: result === "VERIFIED",
    remaining_gap: result === "VERIFIED" ? null : "recognition",
    changes: { concept: { concept_id: "c", name: "Kinematics", before: "fragile", after: result === "VERIFIED" ? "verified" : "fragile" }, strategy: null },
  },
});

const respond = (status: number, body: unknown) => vi.fn(async () => new Response(JSON.stringify(body), { status }));

describe("API client", () => {
  it("sends the backend's request shape and returns its response", async () => {
    const fetchMock = respond(200, START);
    vi.stubGlobal("fetch", fetchMock);
    expect(await api.startSession("A ball…", "maria-id")).toEqual(START);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/session$/);
    expect(JSON.parse(init.body as string)).toEqual({ problem: "A ball…", student_id: "maria-id", force_experiment: false });
  });

  it("reads the backend's error shape into an ApiError", async () => {
    vi.stubGlobal("fetch", respond(503, { error: { code: "model_unavailable", message: "Please try again.", retryable: true } }));
    await expect(api.attempt("s1", "hi")).rejects.toMatchObject({ code: "model_unavailable", message: "Please try again.", retryable: true, status: 503 });
  });

  it("an unreachable backend is a retryable network error, never a fake success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await api.attempt("s1", "hi").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "network", retryable: true });
  });

  it("rejects a response that does not have the contract's shape", async () => {
    vi.stubGlobal("fetch", respond(200, { session_id: "s1", phase: "teach" }));
    await expect(api.attempt("s1", "hi")).rejects.toMatchObject({ code: "malformed_response" });
  });

  it("accepts every turn shape the backend sends", () => {
    for (const body of [TEACH, STRESS, verdict("VERIFIED", true), verdict("NOT YET", false)]) expect(checks.attempt(body)).toBe(true);
    expect(checks.attempt({ ...STRESS, follow_up: null })).toBe(false); // a stress test always carries its problem
  });
});

describe("mapping backend turns onto the screens", () => {
  it("the opening turn shows the backend's message and asks for a first idea", async () => {
    vi.stubGlobal("fetch", respond(200, START));
    const { turn } = await backendTutor.begin("problem");
    expect(turn.beats).toContainEqual({ say: [["Before I help, what would you try first?"]] });
    expect(turn.next).toMatchObject({ kind: "reply", first: true });
  });

  it("a teaching turn carries the real diagnosis, method and hint count, and labels an experiment", () => {
    const turn = mapAttempt(TEACH);
    expect(turn.beats).toContainEqual({ diagnosis: TEACH.diagnosis });
    expect(turn.beats).toContainEqual({ method: TEACH.method });
    expect(turn.beats).toContainEqual({ hints: 1 });
    expect(turn.beats).toContainEqual({ log: { b: "Teaching move · experiment", s: "Visual decomposition · Experiment", k: "ai" } });
    expect(turn.beats).toContainEqual({ say: [["You found the time. What does ", { b: "2.04 s" }, " tell you?"]] });
    expect(turn.next).toMatchObject({ kind: "reply", first: false });
  });

  it("a stress test shows the backend's fresh problem with no support", () => {
    const turn = mapAttempt(STRESS);
    expect(turn.beats).toContainEqual({ dim: true });
    expect(turn.next).toEqual({ kind: "stress", kicker: "Fresh problem · no hints", problem: STRESS.follow_up!.problem, placeholder: "Show how you solve it…" });
  });

  it("VERIFIED ends the session with the seal; a first NOT YET goes back to teaching; a final NOT YET ends it", () => {
    const verified = mapAttempt(verdict("VERIFIED", true));
    expect(verified.beats).toContainEqual({ seal: true });
    expect(verified.next).toBeNull();
    expect(mapAttempt(verdict("NOT YET", false)).next).toMatchObject({ kind: "reply" });
    expect(mapAttempt(verdict("NOT YET", true)).next).toMatchObject({ kind: "ended" });
  });

  it("message text keeps the backend's words; only paragraphs and bold are rendered", () => {
    expect(fromText("One.\n\nTwo **three**.")).toEqual([["One."], ["Two ", { b: "three" }, "."]]);
  });
});

describe("learner views", () => {
  const strategies: StrategyView = {
    student_id: "m",
    display_name: "Maria",
    is_seeded: true,
    rows: [
      { gap: "recognition", method: "socratic", uses: 5, independent_successes: 3, experiments: 0 },
      { gap: "recognition", method: "visual_decomposition", uses: 9, independent_successes: 7, experiments: 0 },
      { gap: "procedure", method: "worked_example", uses: 6, independent_successes: 5, experiments: 0 },
    ],
    methods: [],
  };

  it("groups every gap the backend returns, best first by the backend's smoothed score", () => {
    const groups = strategyGroups(strategies);
    expect(groups.map((g) => g.gap)).toEqual(["recognition", "procedure"]);
    expect(groups[0].rows.map((r) => r.method)).toEqual(["visual_decomposition", "socratic"]);
    expect(groups[0].best?.method).toBe("visual_decomposition");
  });

  it("proven concepts are the backend's verified ones", () => {
    const learner = { student_id: "m", display_name: "Maria", is_seeded: true, concepts: [
      { concept_id: "a", name: "A", state: "verified" as const, evidence: [] },
      { concept_id: "b", name: "B", state: "fragile" as const, evidence: [] },
    ] };
    expect(provenConcepts(learner).map((c) => c.name)).toEqual(["A"]);
  });

  it("an unreachable backend is an error, not seeded stand-in data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(loadViews()).rejects.toMatchObject({ code: "network" });
  });
});
