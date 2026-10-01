"use client";

import type { Answer } from "@/lib/tutor/types";
import { useApp } from "./AppProvider";
import { Icon } from "./Icons";
import { RichText } from "./RichText";

export function QuickView({ answer, onMaster, onBack }: { answer: Answer; onMaster: () => void; onBack: () => void }) {
  const { state } = useApp();
  return (
    <section className="view">
      <div className="quick">
        <p className="eyebrow">Simple</p>
        <h2>
          Here is how it <em>works out.</em>
        </h2>
        <div className="paper">
          <p className="muted" style={{ margin: "0 0 14px" }}>{state.problem.trim()}</p>
          <div className="result">
            <span className="ic">
              <Icon id="i-chart" />
            </span>
            <span>
              <RichText value={answer.result} />
            </span>
          </div>
          <ol className="steps">
            {answer.steps.map((step, i) => (
              <li key={i}>
                <span className="sn">{i + 1}</span>
                <p>
                  <RichText value={step} />
                </p>
              </li>
            ))}
          </ol>
          <div className="note" style={{ marginTop: 18 }}>
            <Icon id="i-info" />
            <span>Simple answers never count as evidence of what you understand.</span>
          </div>
        </div>
        <p className="lede" style={{ margin: "26px 0 14px" }}>Got it, but will it stick? One fresh problem and you will know.</p>
        <div className="row">
          <button className="btn btn-accent" type="button" onClick={onMaster}>
            Try it in Master <Icon id="i-mountain" className="arr" />
          </button>
          <button className="btn-ghost" type="button" onClick={onBack}>Another problem</button>
        </div>
      </div>
    </section>
  );
}
