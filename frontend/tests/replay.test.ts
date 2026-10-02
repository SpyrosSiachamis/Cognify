import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { checks } from "../lib/api";
import { RECORDINGS, replay } from "../lib/tutor/replay";
import type { Beat } from "../lib/tutor/types";

// A replay must be exactly what the backend could have sent: every recorded response passes the app's own API checks,
// and the screens play it through the real mapping all the way to the VERIFIED seal.
describe.each(Object.values(RECORDINGS))("replay: $id", (recording) => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("records only responses the backend contract accepts", () => {
    expect(checks.start(recording.start)).toBe(true);
    for (const step of recording.steps) expect(checks.attempt(step.response)).toBe(true);
  });

  it("plays from the first idea to VERIFIED, pre-filling each answer the student sent", async () => {
    const { tutor, loadViews } = replay(recording);
    const before = await loadViews();
    const opening = tutor.begin(recording.problem);
    await vi.runAllTimersAsync();
    const { session, turn } = await opening;
    let next = turn.next;
    const beats: Beat[] = [...turn.beats];
    for (const step of recording.steps) {
      expect(next && next.kind !== "ended" ? next.prefill : undefined).toBe(step.student);
      const sent = session.send({ text: step.student });
      await vi.runAllTimersAsync();
      const played = await sent;
      beats.push(...played.beats);
      next = played.next;
    }
    expect(next).toBeNull();
    expect(beats.some((b) => "seal" in b)).toBe(true);
    const verdict = beats.find((b) => "verdict" in b);
    expect(verdict && "verdict" in verdict && verdict.verdict.result).toBe("VERIFIED");
    expect(beats.filter((b) => "log" in b && b.log.b.startsWith("Trace · ")).length).toBeGreaterThan(5);
    const after = await loadViews();
    const proven = (v: typeof before) => v.learner.concepts.filter((c) => c.state === "verified").length;
    expect(proven(after)).toBe(proven(before) + 1);
  });
});
