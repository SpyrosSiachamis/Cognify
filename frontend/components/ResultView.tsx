"use client";

import { useEffect, useState } from "react";
import { prefersReducedMotion } from "@/lib/fx";
import { downloadRecording } from "@/lib/tutor/recorder";
import type { Recording } from "@/lib/tutor/replay";
import { gapLabel, strategyLabel } from "@/lib/vocab";
import { useApp } from "./AppProvider";
import { Icon } from "./Icons";

/* After the seal: what the backend changed for the learner (concept state) and for the teacher (strategy counts).
   Every number and label comes from the verdict the backend returned. */
type SaveReplay = () => Promise<{ recording: Recording; stored: boolean }>;
type Saving = { status: "idle" | "saving" } | { status: "saved"; recording: Recording; stored: boolean } | { status: "error"; message: string };

export function ResultView({ onNewProblem, onSaveReplay }: { onNewProblem: () => void; onSaveReplay?: SaveReplay }) {
  const { state, dispatch } = useApp();
  const [saving, setSaving] = useState<Saving>({ status: "idle" });
  const save = () => {
    if (!onSaveReplay || saving.status === "saving") return;
    setSaving({ status: "saving" });
    onSaveReplay()
      .then(({ recording, stored }) => setSaving({ status: "saved", recording, stored }))
      .catch((e) => setSaving({ status: "error", message: e instanceof Error ? e.message : String(e) }));
  };
  const verdict = state.session.verdict;
  const [shown, setShown] = useState(false); // the "after" values replace the "before" ones after a beat

  useEffect(() => {
    const t = setTimeout(() => setShown(true), prefersReducedMotion() ? 0 : 900);
    return () => clearTimeout(t);
  }, []);

  if (!verdict)
    return (
      <section className="view">
        <div className="paper">
          <div className="empty">No verdict yet. Finish a Master session to see what changed.</div>
        </div>
      </section>
    );

  const { concept, strategy } = verdict.changes;
  return (
    <section className="view">
      <div className="vhead">
        {verdict.result === "VERIFIED" && (
          <span className="vbadge">
            <Icon id="i-check" />
            Verified
          </span>
        )}
        <span className="pillbtn">
          <b>{state.session.hintsUsed}</b> {state.session.hintsUsed === 1 ? "hint" : "hints"} before the fresh problem
        </span>
      </div>
      <h2>
        Both learners <em>just learned.</em>
      </h2>
      <p className="lede" style={{ marginBottom: 18 }}>{verdict.evidence}</p>
      <div className="twin">
        <div className="paper">
          <div className="side-title">
            <h3>What you understand</h3>
            <span className="kicker">{concept.name}</span>
          </div>
          <ul className="ladder">
            <li data-s={shown ? concept.after : concept.before} className={shown ? "flip" : undefined}>
              <span className="node" />
              <span className="lt">
                <b>{concept.name}</b>
                <span>{shown ? `was ${concept.before}` : "before this session"}</span>
              </span>
              <span className={`pill ${shown ? concept.after : concept.before}`}>{shown ? concept.after : concept.before}</span>
            </li>
          </ul>
          <div className="twin-note">{verdict.independent ? "Solved on your own: no help on the fresh problem." : "Not counted as independent."}</div>
        </div>
        <div className="paper">
          <div className="side-title">
            <h3>How Cognify teaches you</h3>
          </div>
          {strategy ? (
            <div>
              <span className="kicker">
                {strategyLabel(strategy.method)} · {gapLabel(strategy.gap)}
              </span>
              <div className="odo">
                <span className="v">{(shown ? strategy.after : strategy.before).independent_successes}</span>
                <small>/</small>
                <span className="v">{(shown ? strategy.after : strategy.before).uses}</span>
                <small>independent</small>
                <span className="was">{shown ? `was ${strategy.before.independent_successes} / ${strategy.before.uses}` : ""}</span>
              </div>
            </div>
          ) : (
            <div className="empty">No teaching method was used in this session, so no strategy was credited.</div>
          )}
          <div className="twin-note">A strategy only gains credit when you succeed on a problem you have not seen.</div>
        </div>
      </div>
      <p className="closing">
        It did not stop when the explanation made sense. <span>It stopped when you could solve the next one without it.</span>
      </p>
      <div className="row" style={{ marginTop: 24 }}>
        <button className="btn btn-accent" type="button" onClick={() => dispatch({ type: "sheet", open: true, tab: "overview" })}>
          See all your progress <Icon id="i-chart" className="arr" />
        </button>
        <button className="btn-ghost" type="button" onClick={onNewProblem}>Next problem</button>
        {onSaveReplay && saving.status !== "saved" && (
          <button className="btn-ghost" type="button" onClick={save} disabled={saving.status === "saving"}>
            {saving.status === "saving" ? "Saving…" : "Save as replay"}
          </button>
        )}
      </div>
      {saving.status === "saved" && (
        <p className="demo-note" role="status">
          {saving.stored ? "Saved as a replay in this browser. " : "This browser would not store it; download the file instead. "}
          {saving.stored && (
            <a className="link" href={`/replay/saved?id=${encodeURIComponent(saving.recording.id)}`}>
              Open the replay
            </a>
          )}
          {saving.stored && " · "}
          <button type="button" className="link" onClick={() => downloadRecording(saving.recording)}>
            Download the file
          </button>
        </p>
      )}
      {saving.status === "error" && (
        <p className="demo-note" role="alert">
          Could not save the replay: {saving.message}
        </p>
      )}
    </section>
  );
}
