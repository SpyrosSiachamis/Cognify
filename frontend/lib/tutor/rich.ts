import type { Rich } from "./types";

/** Length the paragraphs would have as HTML. The typing pause is based on it, like the prototype. */
export function htmlLength(paragraphs: Rich[]): number {
  return paragraphs.reduce((total, p) => {
    const inner = p.reduce((n, seg) => {
      if (typeof seg === "string") return n + seg.length;
      if ("b" in seg) return n + 7 + seg.b.length;
      if ("m" in seg) return n + 26 + seg.m.length;
      return n + 25 + seg.eq.length;
    }, 0);
    return total + inner + 7;
  }, 0);
}
