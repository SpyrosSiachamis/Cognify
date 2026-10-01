"use client";

import type { CSSProperties } from "react";
import { useApp } from "./AppProvider";

// Seeded books on the shelf: one book for every concept already proven.
const SHELF = [
  { n: "Ratios", h: 104, c: "--sp1" },
  { n: "Linear equations", h: 120, c: "--sp2" },
  { n: "Factoring", h: 96, c: "--sp3" },
];

export function Shelf() {
  const { state, dispatch } = useApp();
  const books = SHELF.map((b) => ({ ...b, fresh: false }));
  if (state.verified) books.push({ n: "Quadratic modelling", h: 130, c: "--sp5", fresh: true });
  const slots = Array.from({ length: Math.max(0, 9 - books.length) }, (_, k) => books.length + k);

  return (
    <div className="shelf-wrap">
      <div className="shelf-head">
        <h3 aria-level={2}>Your shelf</h3>
        <span>{state.verified ? "A new book just landed." : "One book for every concept you prove."}</span>
      </div>
      <button className="shelf" type="button" aria-label="Open your progress" onClick={() => dispatch({ type: "sheet", open: true, tab: "understanding" })}>
        <div className="spines">
          {books.map((b) => (
            <span key={b.n} className={`spine${b.fresh ? " new" : ""}`} style={{ "--h": `${b.h}px`, "--c": `var(${b.c})` } as CSSProperties}>
              {b.n}
            </span>
          ))}
          {slots.map((i) => (
            <span key={i} className="spine slot" style={{ "--h": `${96 + (i % 3) * 8}px` } as CSSProperties}>
              +
            </span>
          ))}
        </div>
        <div className="plank" />
      </button>
    </div>
  );
}
