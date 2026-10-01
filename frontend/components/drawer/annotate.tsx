import type { ReactNode } from "react";

// Phrases in the student's first idea that Cognify highlights, with what each one shows.
const MARKS: { re: string; tone: "ok" | "warn"; tag: string }[] = [
  { re: "I know the area is 48|area is 48|length times width is 48|length times width", tone: "ok", tag: "concept" },
  { re: "I don[’']?t see a quadratic|do not see a quadratic|no quadratic|not sure how", tone: "warn", tag: "recognition gap" },
];
/** The student's own words with the evidence highlighted. With tags: small labels after each mark. */
export function annotate(text: string, withTags = true): ReactNode[] {
  // Like the prototype: each phrase is highlighted once, at its first match.
  const found = MARKS.flatMap((mark) => {
    const m = new RegExp(mark.re, "i").exec(text);
    return m ? [{ mark, index: m.index, text: m[0] }] : [];
  }).sort((x, y) => x.index - y.index);
  const out: ReactNode[] = [];
  let last = 0;
  for (const f of found) {
    if (f.index < last) continue; // overlaps an earlier highlight
    if (f.index > last) out.push(text.slice(last, f.index));
    out.push(
      <mark key={f.index} data-t={f.mark.tone === "warn" ? "warn" : undefined}>
        {f.text}
        {withTags && <sup>{f.mark.tag}</sup>}
      </mark>,
    );
    last = f.index + f.text.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
