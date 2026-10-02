"use client";

import { provenConcepts } from "@/lib/backend";
import { useApp } from "../AppProvider";
import { NotVerifiedCard } from "./NotVerifiedCard";

const mmss = (s: number) => String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");

export function OverviewTab() {
  const { state } = useApp();
  const { session, views } = state;
  const learner = views.status === "ok" ? views.data.learner : null;
  const proven = learner ? provenConcepts(learner).length : null;
  return (
    <>
      <div className="metrics">
        <div className="paper metric">
          <span className="kicker">Concepts proven</span>
          <span className="v">{proven ?? "–"}<small>{learner ? `of ${learner.concepts.length} seen` : ""}</small></span>
          <p>Verified on a fresh problem, solved without help.</p>
        </div>
        <div className="paper metric">
          <span className="kicker">Hints this session</span>
          <span className="v">{session.phase ? session.hintsUsed : "–"}</span>
          <p>Teaching moves you needed, counted by Cognify.</p>
        </div>
        <div className="paper metric">
          <span className="kicker">This session</span>
          <span className="v" style={{ fontSize: 28 }}>{session.verdict ? session.verdict.result : session.phase ? "in progress" : "–"}</span>
          <p>{session.verdict ? session.verdict.evidence : "The verdict comes after the fresh problem."}</p>
        </div>
      </div>
      {session.verdict?.result === "NOT YET" && <NotVerifiedCard verdict={session.verdict} hintsUsed={session.hintsUsed} over={session.over} />}
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
      {views.status === "error" && (
        <div className="paper">
          <div className="empty">Your history is unavailable: {views.message}</div>
        </div>
      )}
    </>
  );
}
