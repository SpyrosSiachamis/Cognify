import { describe, expect, it } from "vitest";
import { FrameWatch } from "@/lib/framewatch";

// Feed frames every `ms` from t=1 for `seconds`; return when the watch first said "slow" (or null).
function run(watch: FrameWatch, ms: number, seconds: number, start = 1): number | null {
  for (let t = start; t < start + seconds * 1000; t += ms) if (watch.tick(t)) return t - start;
  return null;
}

describe("FrameWatch", () => {
  it("never calls a 60 fps device weak", () => expect(run(new FrameWatch(), 16.7, 20)).toBeNull());
  it("never calls a steady 45 fps device weak", () => expect(run(new FrameWatch(), 22, 20)).toBeNull());
  it("calls a steady 30 fps device weak", () => expect(run(new FrameWatch(), 33, 20)).not.toBeNull());

  it("calls a 20 fps device weak after the warm-up plus the window (about 5 s)", () => {
    const at = run(new FrameWatch(), 50, 20);
    expect(at).not.toBeNull();
    expect(at!).toBeGreaterThanOrEqual(5000);
    expect(at!).toBeLessThan(5200);
  });

  it("ignores slow frames during the warm-up only", () => {
    const watch = new FrameWatch();
    expect(run(watch, 100, 1.9)).toBeNull(); // slow while loading
    expect(run(watch, 16.7, 10, 1901)).toBeNull(); // then smooth
  });

  it("starts over after reset (page hidden or covered)", () => {
    const watch = new FrameWatch();
    run(watch, 50, 4.5);
    watch.reset();
    expect(run(watch, 50, 4, 10_000)).toBeNull();
  });
});
