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

/** The backend's message text as paragraphs. Blank lines split paragraphs and **text** is bold;
    the words themselves are shown exactly as the backend sent them. */
export function fromText(text: string): Rich[] {
  return text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => p.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((s) => (/^\*\*[^*]+\*\*$/.test(s) ? { b: s.slice(2, -2) } : s)));
}
