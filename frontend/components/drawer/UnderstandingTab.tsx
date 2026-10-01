"use client";

import { CONCEPT_NODE } from "@/lib/backend";
import { EDGES, LADDER, NODES, RUNGS, type ConceptNode, type Strength } from "@/lib/progress-data";
import { useApp } from "../AppProvider";

const COLOR: Record<Strength, string> = {
  strong: "var(--c-strong)",
  fragile: "var(--c-fragile)",
  weak: "var(--c-weak)",
  untested: "var(--c-untested)",
  verified: "var(--c-verified)",
};

// The concept as it is now: after today's verified transfer some nodes change.
const nodeNow = (n: ConceptNode, verified: boolean): ConceptNode => (verified && n.after ? { ...n, ...n.after } : n);

// A repeatable scatter of faint stars behind the constellation.
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

function Constellation({ nodes, selected, onSelect }: { nodes: ConceptNode[]; selected: string; onSelect: (id: string) => void }) {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  return (
    <svg id="mapSvg" viewBox="0 0 1000 560" role="group" aria-label="Concept map">
      {STARS.map((s, i) => (
        <circle key={i} cx={s.cx} cy={s.cy} r={s.r} style={{ fill: "var(--accent-2)" }} opacity={s.o} />
      ))}
      {EDGES.map(([a, b], i) => {
        const A = byId[a], B = byId[b];
        const mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2, dx = B.x - A.x, dy = B.y - A.y;
        const len = Math.hypot(dx, dy) || 1, off = (i % 2 ? 1 : -1) * 22;
        const lit = A.st === "verified" && B.st === "verified";
        return <path key={a + b} className={`edge${lit ? " lit" : ""}`} d={`M${A.x} ${A.y} Q${(mx - (dy / len) * off).toFixed(1)} ${(my + (dx / len) * off).toFixed(1)} ${B.x} ${B.y}`} />;
      })}
      {nodes.map((n) => {
        const r = n.big ? 30 : 19;
        const c = COLOR[n.st];
        const pick = () => onSelect(n.id);
        return (
          <g
            key={n.id}
            className={`nodeg${selected === n.id ? " sel" : ""}`}
            tabIndex={0}
            role="button"
            aria-label={`${n.label}, ${n.st}`}
            transform={`translate(${n.x} ${n.y})`}
            onClick={pick}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                pick();
              }
            }}
          >
            {n.st === "verified" && n.big && <circle className="halo" r={r + 16} style={{ fill: c }} opacity=".4" />}
            <g className="body">
              <circle r={r + 7} style={{ fill: c }} opacity=".14" />
              <circle r={r} style={{ fill: "var(--ground)", stroke: c }} strokeWidth="2.4" strokeDasharray={n.st === "untested" ? "3 4" : undefined} />
              {n.st !== "untested" && <circle r={r * 0.5} style={{ fill: c }} />}
              {n.st === "verified" && (
                <path d={`M${-r * 0.38} 0 L${-r * 0.08} ${r * 0.3} L${r * 0.42} ${-r * 0.3}`} fill="none" style={{ stroke: "var(--ground)" }} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              )}
            </g>
            <text y={r + 30} textAnchor="middle" style={n.big ? { fontSize: 25 } : undefined}>
              {n.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function UnderstandingTab() {
  const { state, dispatch } = useApp();
  // Concepts the backend knows about replace the seeded node of the same name.
  const nodes = NODES.map((n) => {
    const base = nodeNow(n, state.verified);
    const known = state.backend?.learner.concepts.find((c) => CONCEPT_NODE[c.name] === n.id);
    return known ? { ...base, st: known.state as Strength, ev: known.evidence[known.evidence.length - 1] ?? base.ev } : base;
  });
  const node = nodes.find((n) => n.id === state.mapSel) ?? nodes[0];
  const firstBreak = node.lad.findIndex((v) => v === 0);
  return (
    <>
      <div className="mapwrap">
        <div className="night">
          <div className="spread" style={{ marginBottom: 6 }}>
            <h3>Your constellation</h3>
            <span className="kicker" style={{ color: "var(--on-dark-faint)" }}>{state.verified ? "Seeded history + today" : "Seeded history"}</span>
          </div>
          <Constellation nodes={nodes} selected={node.id} onSelect={(id) => dispatch({ type: "mapSel", id })} />
          <div className="legend">
            {(["verified", "strong", "fragile", "weak", "untested"] as Strength[]).map((k) => (
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
            <span className={`pill ${node.st}`}>{node.st}</span>
          </div>
          <h3>{node.label}</h3>
          <p className="evi">{node.ev}</p>
          <span className="kicker" style={{ color: "var(--on-dark-faint)" }}>Where it holds, and where it breaks</span>
          <ul className="rungs" style={{ marginTop: 12 }}>
            {RUNGS.map((r, i) => (
              <li key={r} className={i === firstBreak ? "break" : undefined}>
                <span className={`rg ${node.lad[i] === 1 ? "p" : node.lad[i] === 0 ? "f" : ""}`}>{node.lad[i] === 1 ? "✓" : node.lad[i] === 0 ? "×" : ""}</span>
                <span>
                  {r}
                  {i === firstBreak && <span className="break-tag">breaking point</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="paper">
        <div className="side-title">
          <h3>Quadratic modelling, rung by rung</h3>
          <span className="kicker">{state.verified ? "updated today" : "before today"}</span>
        </div>
        <ul className="ladder">
          {LADDER.map((l) => {
            const s = state.verified ? l[3] : l[2];
            return (
              <li key={l[0]} data-s={s}>
                <span className="node" />
                <span className="lt">
                  <b>{l[0]}</b>
                  <span>{l[1]}</span>
                </span>
                <span className={`pill ${s}`}>{s}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </>
  );
}
