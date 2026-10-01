import type { Rich } from "@/lib/tutor/types";

/* Renders the tiny rich-text format as real elements (no innerHTML). */
export function RichText({ value }: { value: Rich }) {
  return (
    <>
      {value.map((seg, i) => {
        if (typeof seg === "string") return seg;
        if ("b" in seg) return <b key={i}>{seg.b}</b>;
        if ("m" in seg) return <span key={i} className="math">{seg.m}</span>;
        return <span key={i} className="eq">{seg.eq}</span>;
      })}
    </>
  );
}
