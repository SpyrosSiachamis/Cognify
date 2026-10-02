"use client";

import { memo, type CSSProperties } from "react";
import { provenConcepts } from "@/lib/backend";
import { useActions, useAppSelector } from "./AppProvider";

const COLORS = ["--sp1", "--sp2", "--sp3", "--sp5"];

/** One book for every concept the backend has as verified for this learner. */
export const Shelf = memo(function Shelf() {
  const { dispatch } = useActions();
  const views = useAppSelector((s) => s.views);
  const proven = views.status === "ok" ? provenConcepts(views.data.learner) : [];
  const seeded = views.status === "ok" && views.data.learner.is_seeded;
  const books = proven.map((c, i) => ({ n: c.name, h: 96 + ((c.name.length * 7) % 34), c: COLORS[i % COLORS.length] }));
  const slots = Array.from({ length: Math.max(0, 9 - books.length) }, (_, k) => books.length + k);
  const note =
    views.status === "loading" ? "Loading your shelf…" :
    views.status === "error" ? "Your shelf is unavailable while Cognify cannot be reached." :
    books.length === 0 ? "No concept proven yet. One book for every concept you prove." :
    seeded ? "Includes seeded demo history." : "One book for every concept you prove.";

  return (
    <div className="shelf-wrap">
      <div className="shelf-head">
        <h3 aria-level={2}>Your shelf</h3>
        <span>{note}</span>
      </div>
      <button className="shelf" type="button" aria-label="Open your progress" onClick={() => dispatch({ type: "sheet", open: true, tab: "understanding" })}>
        <div className="spines">
          {books.map((b) => (
            <span key={b.n} className="spine" style={{ "--h": `${b.h}px`, "--c": `var(${b.c})` } as CSSProperties}>
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
});
