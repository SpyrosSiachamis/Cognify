"use client";

import { useEffect, useState } from "react";
import { livePolicy } from "@/lib/backend";
import { HINTS, POLICY, policyNow } from "@/lib/progress-data";
import { useApp } from "../AppProvider";
import { Icon } from "../Icons";
import { Spark } from "../Spark";

export function TeachingTab() {
  const { state } = useApp();
  const [on, setOn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setOn(true), 120);
    return () => clearTimeout(t);
  }, []);
  const vals = state.verified ? HINTS.vals : HINTS.vals.slice(0, 5);
  const labels = state.verified ? HINTS.labels : HINTS.labels.slice(0, 5);

  return (
    <>
      <div className="paper">
        <div className="side-title">
          <h3>Which teaching moves work for you</h3>
          <span className="pill seed">Seeded history</span>
        </div>
        <p className="muted" style={{ margin: "-4px 0 6px" }}>
          Ranked by later independent success on fresh problems, by kind of gap. Observed results, not learning styles.
        </p>
        {Object.keys(POLICY).map((gap) => {
          const rows = policyNow(gap, state.verified, livePolicy(state.backend));
          const best = rows.reduce((b, r) => (r.a / r.n > b.a / b.n ? r : b), rows[0]);
          return (
            <div className="gaprow" key={gap}>
              <h4>
                {gap}
                {gap === "Words → equation" && <span className="pill ai">found today</span>}
              </h4>
              {rows.map((r, i) => {
                const bump = state.verified && gap === "Words → equation" && i === 0;
                return (
                  <div key={r.s} className={`srow${r === best ? " best" : ""}${bump ? " bump" : ""}`}>
                    <span>{r.s}</span>
                    <span className="bar2">
                      <i style={{ width: on ? `${((r.a / r.n) * 100).toFixed(0)}%` : 0 }} />
                    </span>
                    <span className="n">
                      {r.a} / {r.n}
                      {r === best ? " ★" : ""}
                    </span>
                  </div>
                );
              })}
            </div>
          );
        })}
        <div className="formula">chosen = argmax over strategies of independent transfer on fresh problems</div>
      </div>
      <div className="paper">
        <div className="side-title">
          <h3>How much help you need</h3>
          <span className="pill seed">Seeded history</span>
        </div>
        <div className="spark">
          <Spark vals={vals} labels={labels} animate />
        </div>
        <div className="note" style={{ marginTop: 14 }}>
          <Icon id="i-info" />
          <span>The AI never grades its own explanation. A strategy only moves up when you succeed on a problem you have not seen.</span>
        </div>
      </div>
    </>
  );
}
