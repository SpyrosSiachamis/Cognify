/* Small helpers for motion: reduced-motion check, waiting, scrolling into view and a spark burst. */

import { room } from "./room";

export const prefersReducedMotion = () => typeof window !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Wait for a while (no waiting at all if the user prefers reduced motion). */
export const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, prefersReducedMotion() ? 0 : ms));

export function lookAt(el: Element | null, block: ScrollLogicalPosition = "end") {
  if (!el) return;
  requestAnimationFrame(() => el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block }));
}

/** A small burst of sparks over an element (like a tiny celebration). */
export function popAt(el: Element | null) {
  if (!el) return;
  const r = el.getBoundingClientRect();
  room.burst(r.left + Math.min(r.width, 120) / 2, r.top + r.height / 2, 34);
}
