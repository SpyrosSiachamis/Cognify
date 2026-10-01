import { afterEach, describe, expect, it, vi } from "vitest";
import { loadBackendData, policyFromStrategies, recordedTutor } from "@/lib/backend";
import { policyNow } from "@/lib/progress-data";
import { scriptedTutor } from "@/lib/tutor/scripted";
import type { StrategyView } from "@/lib/api";

const strategies: StrategyView = {
  student_id: "16e82ef2-adee-4671-8393-c6b50ac91672",
  display_name: "Maria",
  is_seeded: true,
  rows: [
    { gap: "recognition", method: "socratic", uses: 5, independent_successes: 3, experiments: 0 },
    { gap: "recognition", method: "visual_decomposition", uses: 9, independent_successes: 7, experiments: 0 },
    { gap: "procedure", method: "worked_example", uses: 6, independent_successes: 5, experiments: 0 },
  ],
  methods: [],
};

afterEach(() => vi.unstubAllGlobals());

describe("backend data on the Progress screens", () => {
  it("maps recognition rows to the words-to-equation gap, best first, and ignores unknown gaps", () => {
    const policy = policyFromStrategies(strategies);
    expect(Object.keys(policy)).toEqual(["Words → equation"]);
    expect(policy["Words → equation"]).toEqual([
      { s: "Visual + Socratic", a: 7, n: 9 },
      { s: "Socratic questions", a: 3, n: 5 },
    ]);
  });

  it("live rows win over the seeded ones; without them today's win bumps 7/9 to 8/10", () => {
    expect(policyNow("Words → equation", false, policyFromStrategies(strategies))[0]).toEqual({ s: "Visual + Socratic", a: 7, n: 9 });
    expect(policyNow("Words → equation", true)[0]).toEqual({ s: "Visual + Socratic", a: 8, n: 10 });
    expect(policyNow("Words → equation", false)[0]).toEqual({ s: "Visual + Socratic", a: 7, n: 9 });
  });

  it("falls back to null (seeded history) when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    expect(await loadBackendData()).toBeNull();
  });
});

describe("recording a Master session on the backend", () => {
  const verdict = {
    session_id: "s1",
    phase: "verdict",
    session_over: true,
    verdict: {
      result: "VERIFIED",
      evidence: "ok",
      independent: true,
      remaining_gap: null,
      changes: {
        concept: { concept_id: "c", name: "Constant-acceleration kinematics", before: "fragile", after: "verified" },
        strategy: { gap: "recognition", method: "visual_decomposition", before: { uses: 9, independent_successes: 7 }, after: { uses: 10, independent_successes: 8 } },
      },
    },
  };

  it("sends the idea, the warm-up and the fresh problem, and reports a verified verdict", async () => {
    const calls: string[] = [];
    let attempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? "GET"} ${url.replace(/^.*:8000/, "")}`);
        // Like the real backend: the first two attempts are teaching turns, the third gets the verdict.
        const teach = { session_id: "s1", phase: "teach", message: "m", hints_used: 0 };
        const body = url.endsWith("/api/session") ? { session_id: "s1", phase: "ask_first_thought", message: "m", hints_used: 0 } : ++attempts < 3 ? teach : verdict;
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
    const seen: unknown[] = [];
    const tutor = recordedTutor(scriptedTutor, (changes) => seen.push(changes));
    const { session } = await tutor.begin("problem");
    await session.send({ text: "my idea", kind: "idea" });
    await session.send({ text: "x + (x + 3) = 25", kind: "probe" });
    await session.send({ text: "x + 2", kind: "question" }); // a Socratic answer is not sent to the backend
    await session.send({ text: "x(x + 2) = 48", kind: "question" });
    await session.send({ text: "", kind: "ready" });
    await session.send({ text: "x(x+2)=168", answer: "12", kind: "transfer" });
    await vi.waitFor(() => expect(seen).toHaveLength(1));
    expect(calls.filter((c) => c.includes("/attempt"))).toHaveLength(3);
    expect(calls[0]).toBe("POST /api/session");
  });

  it("keeps the screens working when the backend is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const tutor = recordedTutor(scriptedTutor, () => {});
    const { session, turn } = await tutor.begin("problem");
    expect(turn.next?.kind).toBe("idea");
    const reply = await session.send({ text: "my idea", kind: "idea" });
    expect(reply.accepted).toBe(true);
  });
});
