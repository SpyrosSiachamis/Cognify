/* Notices a device that cannot keep up: frames that stay slow for a few seconds in a row. */

export class FrameWatch {
  private first = 0;
  private times: number[] = [];

  /**
   * @param warmupMs   ignore the first moments after (re)starting, when loading makes every page slow
   * @param windowMs   how long frames must stay slow before we call the device weak
   * @param slowMs     an average frame longer than this (25 ms = under 40 fps) counts as slow
   */
  constructor(private warmupMs = 2000, private windowMs = 3000, private slowMs = 25) {}

  /** Start again, for example after the page was hidden or covered. */
  reset() {
    this.first = 0;
    this.times = [];
  }

  /** Call once per animation frame with its timestamp. True when the last few seconds were slow. */
  tick(t: number): boolean {
    if (!this.first) this.first = t;
    if (t - this.first < this.warmupMs) return false;
    this.times.push(t);
    while (this.times.length > 2 && t - this.times[1] >= this.windowMs) this.times.shift();
    const span = t - this.times[0];
    if (this.times.length < 2 || span < this.windowMs) return false;
    return span / (this.times.length - 1) > this.slowMs;
  }
}
