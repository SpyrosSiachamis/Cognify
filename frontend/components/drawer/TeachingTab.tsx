"use client";

import { useEffect, useState } from "react";
import { strategyGroups } from "@/lib/backend";
import { gapLabel, modeLabel, strategyLabel } from "@/lib/vocab";
import { useApp } from "../AppProvider";
import { Icon } from "../Icons";

/* Which teaching moves have worked for this learner (GET /api/strategies) and the move chosen this session. */
export function TeachingTab() {
  const { state } = useApp();
  const [on, setOn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setOn(true), 120);
    return () => clearTimeout(t);
  }, []);
  const views = state.views;
  const method = state.session.method;
  const groups = views.status === "ok" ? strategyGroups(views.data.strategies) : [];

  return (
    <>
      {method && (
        <div className="paper stack">
          <div className="side-title">
            <h3>This session’s teaching move</h3>
            <span className={`pill ${method.experiment ? "fragile" : "ai"}`}>{method.experiment ? "Experiment" : modeLabel(method.mode)}</span>
          </div>
          <p style={{ margin: 0 }}>
            <b>{strategyLabel(method.name)}</b>
          </p>
          <p className="muted" style={{ margin: 0 }}>{method.reason}</p>
          {method.experiment && (
            <div className="note">
              <Icon id="i-info" />
              <span>This move is an experiment: Cognify is testing whether another method works better for you. It is recorded as one.</span>
            </div>
          )}
        </div>
      )}
      <div className="paper">
        <div className="side-title">
          <h3>Which teaching moves work for you</h3>
          {views.status === "ok" && views.data.strategies.is_seeded && <span className="pill seed">Seeded history</span>}
        </div>
        <p className="muted" style={{ margin: "-4px 0 6px" }}>
          Ranked by later independent success on fresh problems, by kind of gap. Observed results, not learning styles.
        </p>
        {views.status === "loading" && <div className="empty">Loading…</div>}
        {views.status === "error" && <div className="empty">Unavailable: {views.message}</div>}
        {views.status === "ok" && groups.length === 0 && <div className="empty">No teaching history yet.</div>}
        {groups.map((g) => (
          <div className="gaprow" key={g.gap}>
            <h4>{gapLabel(g.gap)}</h4>
            {g.rows.map((r) => {
              const best = r === g.best;
              return (
                <div key={r.method} className={`srow${best ? " best" : ""}`}>
                  <span>{strategyLabel(r.method)}</span>
                  <span className="bar2">
                    <i style={{ width: on && r.uses ? `${((r.independent_successes / r.uses) * 100).toFixed(0)}%` : 0 }} />
                  </span>
                  <span className="n">
                    {r.independent_successes} / {r.uses}
                    {best ? " ★" : ""}
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <div className="paper">
        <div className="note">
          <Icon id="i-info" />
          <span>The AI never grades its own explanation. A strategy only moves up when you succeed on a problem you have not seen.</span>
        </div>
      </div>
    </>
  );
}
