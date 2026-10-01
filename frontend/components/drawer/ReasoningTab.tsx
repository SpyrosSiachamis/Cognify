"use client";

import { useEffect, useState } from "react";
import type { Confidence } from "@/lib/vocab";
import { gapLabel, roleLabel } from "@/lib/vocab";
import { useApp } from "../AppProvider";
import { Icon } from "../Icons";
import { annotate } from "./annotate";

// Confidence is a label, never a number. The ring only shows roughly how full each label is.
const FILL: Record<Confidence, number> = { low: 22, medium: 55, high: 85 };
const STATUS_PILL: Record<string, string> = { correct: "strong", wrong: "weak", missing: "untested" };

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

/* What the reasoning step read in the student's latest diagnosed answer (TutorTurn.diagnosis). */
export function ReasoningTab() {
  const { state } = useApp();
  const [on, setOn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setOn(true), 250);
    return () => clearTimeout(t);
  }, []);
  const { diagnosis, diagnosedText } = state.session;

  if (!diagnosis)
    return (
      <div className="paper">
        <div className="empty">
          Nothing to read yet. Once you answer in a Master session, this is where Cognify shows how it read your reasoning.
          A turn that moves straight to the fresh problem carries no new reading.
        </div>
      </div>
    );

  return (
    <>
      <div className="paper stack">
        <div className="side-title">
          <h3>What you wrote</h3>
          <span className="pill ai">The answer Cognify read</span>
        </div>
        <div className="annot">{annotate(diagnosedText, diagnosis.steps)}</div>
      </div>
      <div className="paper">
        <div className="side-title">
          <h3>Your steps, as Cognify read them</h3>
        </div>
        <ul className="signals">
          {diagnosis.steps.map((step, i) => (
            <li key={i}>
              <span className="nm">{roleLabel(step.role)}</span>
              <span className={`pill ${STATUS_PILL[step.status] ?? ""}`}>{step.status}</span>
              <span className="why">{step.quote ? `“${step.quote}”` : "Not in your answer yet."}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="paper stack">
        <div className="side-title">
          <h3>{diagnosis.alternatives.length ? "Possible gaps" : "The gap"}</h3>
          <span className="kicker">confidence from the evidence</span>
        </div>
        {diagnosis.main_gap ? (
          <div className="hyps">
            <Hypothesis cls="win" level={diagnosis.confidence} title={gapLabel(diagnosis.main_gap)} text="The gap that best explains where this answer stops or goes wrong." on={on} />
            {diagnosis.alternatives.map((alt) => (
              <Hypothesis key={alt.gap} cls="alt" level={alt.confidence} title={gapLabel(alt.gap)} text="Another reading the same evidence could support." on={on} />
            ))}
          </div>
        ) : (
          <div className="note ai">
            <Icon id="i-info" />
            <span>No gap shown in this answer. Cognify either found every step sound or needs more of your reasoning before it names one.</span>
          </div>
        )}
      </div>
    </>
  );
}
