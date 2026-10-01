"use client";

import { useEffect, useState } from "react";
import type { Confidence } from "@/lib/vocab";
import { SIGNALS } from "@/lib/progress-data";
import { useApp } from "../AppProvider";
import { Icon } from "../Icons";
import { annotate } from "./annotate";

// Confidence is a label, never a number. The ring only shows roughly how full each label is.
const FILL: Record<Confidence, number> = { low: 22, medium: 55, high: 85 };

function Hypothesis({ cls, level, title, text, on }: { cls: string; level: Confidence; title: string; text: string; on: boolean }) {
  return (
    <div className={`hyp ${cls}`.trim()}>
      <div className="ring">
        <svg viewBox="0 0 100 100">
          <circle className="trk" cx="50" cy="50" r="42" />
          <circle className="val" cx="50" cy="50" r="42" pathLength="100" style={{ strokeDasharray: `${on ? FILL[level] : 0} 100` }} />
        </svg>
        <span className="num">{level}</span>
      </div>
      <div>
        <div className="t">{title}</div>
        <div className="d">{text}</div>
      </div>
    </div>
  );
}

export function ReasoningTab() {
  const { state } = useApp();
  const [on, setOn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setOn(true), 250);
    return () => clearTimeout(t);
  }, []);

  if (!state.shared)
    return (
      <div className="paper">
        <div className="empty">Nothing to read yet. Once you share your first idea in a Master session, this is where Cognify shows how it understood your thinking.</div>
      </div>
    );

  const [a, b]: Confidence[] = state.probed ? ["high", "low"] : ["medium", "low"];
  const gaps: [string, string][] = [
    ["Recognition", "fragile"],
    ["Representation", "weak"],
    ["Concept", "strong"],
    ["Procedure", state.probed ? "strong" : "untested"],
    ["Transfer", state.verified ? "verified" : "untested"],
  ];
  return (
    <>
      <div className="paper stack">
        <div className="side-title">
          <h3>What you wrote</h3>
          <span className="pill ai">Your first idea</span>
        </div>
        <div className="annot">{annotate(state.thought)}</div>
      </div>
      <div className="paper">
        <div className="side-title">
          <h3>What Cognify read in it</h3>
        </div>
        <ul className="signals">
          {SIGNALS.map(([name, level, why]) => (
            <li key={name}>
              <span className="nm">{name}</span>
              <span className={`pill ${level}`}>{level}</span>
              <span className="why">{why}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="paper stack">
        <div className="side-title">
          <h3>Two possible gaps</h3>
          <span className="kicker">confidence from the evidence</span>
        </div>
        <div className="hyps">
          <Hypothesis cls={state.probed ? "win" : ""} level={a} title="Words → equation" text="The idea is there. Turning “2 m greater” into algebra is where it stalls." on={on} />
          <Hypothesis cls={`alt${state.probed ? " fade" : ""}`} level={b} title="Spotting the quadratic" text="The problem may not look quadratic until it is written as an equation." on={on} />
        </div>
        <blockquote className="evidence">
          {annotate(state.thought, false)}
          <cite>Evidence · your first idea</cite>
        </blockquote>
        {state.probed && (
          <div className="note ai">
            <Icon id="i-check" />
            <span>
              <b>Diagnosis.</b> Algebra is fine. The gap shows up when a relation hides inside an area, like modelling “2 m greater” as a side length.
            </span>
          </div>
        )}
        <div className="gapgrid">
          {gaps.map(([k, v]) => (
            <div key={k}>
              <span>{k}</span>
              <span className={`pill ${v}`}>{v}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
