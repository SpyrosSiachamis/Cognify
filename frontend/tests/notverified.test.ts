import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Verdict } from "@/lib/api";
import { NotVerifiedCard } from "@/components/drawer/NotVerifiedCard";
import { mapAttempt } from "@/lib/tutor/backend";

const base: Verdict = {
  result: "NOT YET",
  evidence: "Started by finding the time again instead of the equation that needs no time.",
  independent: true,
  remaining_gap: "recognition",
  changes: { concept: { concept_id: "c", name: "Constant-acceleration kinematics", before: "fragile", after: "fragile" }, strategy: null },
};
const html = (v: Verdict, hints = 1, over = false) => renderToStaticMarkup(createElement(NotVerifiedCard, { verdict: v, hintsUsed: hints, over }));

describe("why it is not verified yet", () => {
  it("own work but not correct: says the answer was not correct yet and names the open gap", () => {
    const out = html(base);
    expect(out).toContain(base.evidence);
    expect(out).toContain("was not correct yet");
    expect(out).toContain("Recognising the method");
    expect(out).toContain("goes back to teaching");
  });

  it("too much help: says it was not counted as own work and gives the hint count", () => {
    const out = html({ ...base, independent: false }, 4);
    expect(out).toContain("You needed 4 hints");
    expect(out).toContain("not counted");
  });

  it("after the last try: says the session has ended", () => {
    expect(html(base, 1, true)).toContain("This session has ended");
  });

  it("a NOT YET turn points the student to Progress", () => {
    const turn = mapAttempt({ session_id: "s", phase: "verdict", session_over: false, verdict: base });
    expect(turn.beats).toContainEqual({ toast: { msg: "Not verified yet. See why", label: "See why", tab: "overview" } });
  });
});
