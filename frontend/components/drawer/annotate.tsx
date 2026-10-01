import type { ReactNode } from "react";
import type { Step } from "@/lib/api";
import { roleLabel } from "@/lib/vocab";

/** The student's own words with the diagnosis's evidence highlighted: each step quote the backend returned is
    marked where it appears in the text, green when the step holds, red when it is wrong or missing.
    A quote that cannot be found in the text is not highlighted. */
export function annotate(text: string, steps: Step[], withTags = true): ReactNode[] {
  const lower = text.toLowerCase();
  const found = steps
    .flatMap((step) => {
      const quote = step.quote?.trim();
      if (!quote) return [];
      const index = lower.indexOf(quote.toLowerCase());
      return index < 0 ? [] : [{ step, index, length: quote.length }];
    })
    .sort((x, y) => x.index - y.index || y.length - x.length);
  const out: ReactNode[] = [];
  let last = 0;
  for (const f of found) {
    if (f.index < last) continue; // overlaps an earlier highlight
    if (f.index > last) out.push(text.slice(last, f.index));
    out.push(
      <mark key={f.index} data-t={f.step.status === "correct" ? undefined : "warn"}>
        {text.slice(f.index, f.index + f.length)}
        {withTags && <sup>{`${roleLabel(f.step.role)} · ${f.step.status}`}</sup>}
      </mark>,
    );
    last = f.index + f.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
