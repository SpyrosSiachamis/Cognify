import { describe, expect, it } from "vitest";
import { DEMO_THOUGHT } from "@/lib/state";
import { checkArea, checkLength, checkTransfer, checkWarmUp, scriptedTutor } from "@/lib/tutor/scripted";

describe("answer checks", () => {
  it("accepts the length written either way round, ignoring spaces", () => {
    expect(checkLength("x + 2")).toBe(true);
    expect(checkLength("2+x")).toBe(true);
    expect(checkLength("length = x + 2")).toBe(true);
    expect(checkLength("x + 3")).toBe(false);
  });

  it("accepts the area equation in its usual forms and needs the 48", () => {
    expect(checkArea("x(x + 2) = 48")).toBe(true);
    expect(checkArea("(x+2)x=48")).toBe(true);
    expect(checkArea("x² + 2x = 48")).toBe(true);
    expect(checkArea("x(x + 2)")).toBe(false);
    expect(checkArea("x + x + 2 = 48")).toBe(false);
  });

  it("recognises a good warm-up equation", () => {
    expect(checkWarmUp("x + (x + 3) = 25")).toBe(true);
    expect(checkWarmUp("2s + 3 = 25")).toBe(true);
    expect(checkWarmUp("s + 3 = 25")).toBe(false);
  });

  it("accepts 12 or -14 for the fresh problem", () => {
    expect(checkTransfer("12")).toBe(true);
    expect(checkTransfer("-14")).toBe(true);
    expect(checkTransfer("12,0")).toBe(true);
    expect(checkTransfer("14")).toBe(false);
    expect(checkTransfer("")).toBe(false);
  });
});

describe("scripted Master session", () => {
  it("walks the whole scenario and only verifies at the end", async () => {
    const { session, turn } = await scriptedTutor.begin("any problem");
    expect(turn.next?.kind).toBe("idea");

    const idea = await session.send({ text: DEMO_THOUGHT });
    expect(idea.next?.kind).toBe("probe");
    expect(idea.beats.some((b) => "mark" in b && b.mark === "shared")).toBe(true);

    const probe = await session.send({ text: "x + (x + 3) = 25" });
    expect(probe.next?.kind).toBe("question");

    const wrong = await session.send({ text: "x + 3" });
    expect(wrong.accepted).toBe(false);
    expect(wrong.next?.kind).toBe("question");

    const q1 = await session.send({ text: "x + 2" });
    expect(q1.accepted).toBe(true);
    expect(q1.feedback?.tone).toBe("good");

    const q2 = await session.send({ text: "x(x + 2) = 48" });
    expect(q2.next?.kind).toBe("ready");
    expect(q2.beats.some((b) => "built" in b)).toBe(true);

    const ready = await session.send({ text: "" });
    expect(ready.next?.kind).toBe("transfer");
    expect(ready.beats).toContainEqual({ dim: true });

    const notYet = await session.send({ text: "x(x+2)=168", answer: "14" });
    expect(notYet.accepted).toBe(false);
    expect(notYet.beats.some((b) => "seal" in b)).toBe(false);

    const done = await session.send({ text: "x(x+2)=168", answer: "12" });
    expect(done.accepted).toBe(true);
    expect(done.beats.some((b) => "seal" in b)).toBe(true);
    expect(done.next).toBeNull();
  });

  it("asks again when an answer box is empty", async () => {
    const { session } = await scriptedTutor.begin("p");
    await session.send({ text: "idea" });
    await session.send({ text: "x + (x + 3) = 25" });
    const empty = await session.send({ text: "  " });
    expect(empty.accepted).toBe(false);
    expect(empty.feedback?.text).toBe("Type an expression using x.");
  });
});
