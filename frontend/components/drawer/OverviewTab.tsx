"use client";

import { livePolicy } from "@/lib/backend";
import { HINTS, policyNow } from "@/lib/progress-data";
import { BASE } from "@/lib/state";
import { useApp } from "../AppProvider";
import { Spark } from "../Spark";

const mmss = (s: number) => String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");

export function OverviewTab() {
  const { state } = useApp();
  const row = policyNow("Words → equation", state.verified, livePolicy(state.backend))[0];
  const streak = BASE.streak + (state.verified ? 1 : 0);
  const vals = state.verified ? HINTS.vals : HINTS.vals.slice(0, 5);
  const labels = state.verified ? HINTS.labels : HINTS.labels.slice(0, 5);
  return (
    <>
      <div className="metrics">
        <div className="paper metric">
          <span className="kicker">Independent transfers</span>
          <span className="v">{row.a}<small>of {row.n}</small></span>
          <p>Fresh problems solved alone, with the strategy that works for you.</p>
        </div>
        <div className="paper metric">
          <span className="kicker">Hints this session</span>
          <span className="v">{state.shared ? state.hints : "–"}<small>{state.verified ? "then 0 on the test" : ""}</small></span>
          <p>The goal is needing less help every time.</p>
        </div>
        <div className="paper metric">
          <span className="kicker">Day streak</span>
          <span className="v">{streak}<small>days</small></span>
          <p>{state.verified ? "Extended today." : "Verify something today to extend it."}</p>
        </div>
      </div>
      <div className="paper">
        <div className="side-title">
          <h3>This session</h3>
          {state.log.length > 0 && <span className="pill ai">live</span>}
        </div>
        {state.log.length ? (
          <ul className="tl">
            {state.log.map((e, i) => (
              <li key={i} className={e.k}>
                <time>{mmss(e.t)}</time>
                <span className="d" />
                <div>
                  <b>{e.b}</b>
                  <span>{e.s}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="empty">Start a Master session and every step lands here.</div>
        )}
      </div>
      <div className="paper">
        <div className="side-title">
          <h3>Hints needed over time</h3>
          <span className="pill seed">Seeded history</span>
        </div>
        <div className="spark">
          <Spark vals={vals} labels={labels} animate />
        </div>
      </div>
    </>
  );
}
