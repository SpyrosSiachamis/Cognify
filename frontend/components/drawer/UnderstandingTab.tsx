"use client";

import type { LearnerConcept } from "@/lib/api";
import type { State } from "@/lib/vocab";
import { useApp } from "../AppProvider";

const COLOR: Record<State, string> = {
  strong: "var(--c-strong)",
  fragile: "var(--c-fragile)",
  weak: "var(--c-weak)",
  untested: "var(--c-untested)",
  verified: "var(--c-verified)",
};

// A repeatable scatter of faint stars behind the concepts (decoration only).
function stars() {
  let seed = 11;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  return Array.from({ length: 70 }, () => ({
    cx: (rnd() * 1000).toFixed(0),
    cy: (rnd() * 560).toFixed(0),
    r: (0.4 + rnd() * 1.1).toFixed(1),
    o: (0.15 + rnd() * 0.4).toFixed(2),
  }));
}
const STARS = stars();

/** Where each concept sits: evenly spread on an ellipse, in the backend's order. The backend has no map of how
    concepts relate, so no links are drawn between them. */
function layout(count: number, i: number) {
  if (count === 1) return { x: 500, y: 280 };
  const a = -Math.PI / 2 + (2 * Math.PI * i) / count;
  return { x: 500 + 360 * Math.cos(a), y: 280 + 190 * Math.sin(a) };
}

function Constellation({ concepts, selected, onSelect }: { concepts: LearnerConcept[]; selected: string; onSelect: (id: string) => void }) {
  return (
    <svg id="mapSvg" viewBox="0 0 1000 560" role="group" aria-label="Your concepts">
      {STARS.map((s, i) => (
        <circle key={i} cx={s.cx} cy={s.cy} r={s.r} style={{ fill: "var(--accent-2)" }} opacity={s.o} />
      ))}
      {concepts.map((c, i) => {
        const { x, y } = layout(concepts.length, i);
        const r = 24;
        const col = COLOR[c.state] ?? COLOR.untested;
        const pick = () => onSelect(c.concept_id);
        return (
          <g
            key={c.concept_id}
            className={`nodeg${selected === c.concept_id ? " sel" : ""}`}
            tabIndex={0}
            role="button"
            aria-label={`${c.name}, ${c.state}`}
            transform={`translate(${x.toFixed(1)} ${y.toFixed(1)})`}
            onClick={pick}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                pick();
              }
            }}
          >
            <g className="body">
              <circle r={r + 7} style={{ fill: col }} opacity=".14" />
              <circle r={r} style={{ fill: "var(--ground)", stroke: col }} strokeWidth="2.4" strokeDasharray={c.state === "untested" ? "3 4" : undefined} />
              {c.state !== "untested" && <circle r={r * 0.5} style={{ fill: col }} />}
              {c.state === "verified" && (
                <path d={`M${-r * 0.38} 0 L${-r * 0.08} ${r * 0.3} L${r * 0.42} ${-r * 0.3}`} fill="none" style={{ stroke: "var(--ground)" }} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              )}
            </g>
            <text y={r + 30} textAnchor="middle">
              {c.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* What the backend knows about each concept for this learner (GET /api/learner): its state and the evidence behind it. */
export function UnderstandingTab() {
  const { state, dispatch } = useApp();
  const views = state.views;
  if (views.status !== "ok")
    return (
      <div className="paper">
        <div className="empty">{views.status === "loading" ? "Loading your concepts…" : `Your concepts are unavailable: ${views.message}`}</div>
      </div>
    );
  const { learner } = views.data;
  if (learner.concepts.length === 0)
    return (
      <div className="paper">
        <div className="empty">No concepts yet. Finish a Master session and the concept it practised appears here.</div>
      </div>
    );
  const concept = learner.concepts.find((c) => c.concept_id === state.mapSel) ?? learner.concepts[0];
  return (
    <div className="mapwrap">
      <div className="night">
        <div className="spread" style={{ marginBottom: 6 }}>
          <h3>Your concepts</h3>
          <span className="kicker" style={{ color: "var(--on-dark-faint)" }}>{learner.is_seeded ? "Includes seeded demo history" : "From your sessions"}</span>
        </div>
        <Constellation concepts={learner.concepts} selected={concept.concept_id} onSelect={(id) => dispatch({ type: "mapSel", id })} />
        <div className="legend">
          {(["verified", "strong", "fragile", "weak", "untested"] as State[]).map((k) => (
            <span key={k}>
              <i style={{ background: `var(--c-${k})` }} />
              {k[0].toUpperCase() + k.slice(1)}
            </span>
          ))}
        </div>
      </div>
      <div className="night mpanel">
        <div className="spread" style={{ marginBottom: 6 }}>
          <span className="kicker" style={{ color: "var(--on-dark-faint)" }}>Selected concept</span>
          <span className={`pill ${concept.state}`}>{concept.state}</span>
        </div>
        <h3>{concept.name}</h3>
        <span className="kicker" style={{ color: "var(--on-dark-faint)" }}>The evidence behind it</span>
        {concept.evidence.length ? (
          <ul className="rungs" style={{ marginTop: 12 }}>
            {concept.evidence.map((e, i) => (
              <li key={i}>
                <span className="rg p">·</span>
                <span>{e}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="evi">No evidence recorded yet.</p>
        )}
      </div>
    </div>
  );
}
