"use client";

import { useEffect, useState } from "react";
import { pop, prefersReducedMotion } from "@/lib/fx";
import { HINTS, LADDER } from "@/lib/progress-data";
import { BASE } from "@/lib/state";
import { useApp } from "./AppProvider";
import { Icon } from "./Icons";
import { Spark } from "./Spark";

/* After the seal: what changed for the learner (ladder) and for the teacher (7/9 becomes 8/10). */
export function ResultView({ onNewProblem }: { onNewProblem: () => void }) {
  const { state, dispatch } = useApp();
  // The backend's own before and after, when it verified the fresh problem; otherwise the prepared 7/9 to 8/10.
  const strategy = state.verdict?.strategy;
  const before = strategy ? strategy.before : { independent_successes: 7, uses: 9 };
  const after = strategy ? strategy.after : { independent_successes: 8, uses: 10 };
  const [flipped, setFlipped] = useState<boolean[]>(LADDER.map(() => false));
  const [odoStep, setOdoStep] = useState(0); // 0: before, 1: first number changed, 2: second changed, 3: "was ..." shown
  const [fullSpark, setFullSpark] = useState(false);

  useEffect(() => {
    const k = prefersReducedMotion() ? 0 : 1;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const at = (ms: number, fn: () => void) => timers.push(setTimeout(fn, ms * k));

    // The top-bar chips already show the new numbers; give them a little pop.
    at(300, () => pop(document.getElementById("streak")));
    at(650, () => pop(document.getElementById("vchip")));
    at(500, () => setFullSpark(true));
    LADDER.forEach((l, i) => {
      if (l[2] !== l[3]) at(800 + i * 280, () => setFlipped((f) => f.map((v, j) => (j === i ? true : v))));
    });
    // The odometer fades each number out and the new one in.
    at(1200, () => setOdoStep(1));
    at(1350, () => setOdoStep(2));
    at(1750, () => setOdoStep(3));
    return () => timers.forEach(clearTimeout);
  }, []);

  const vals = fullSpark ? HINTS.vals : HINTS.vals.slice(0, 5);
  const labels = fullSpark ? HINTS.labels : HINTS.labels.slice(0, 5);

  return (
    <section className="view">
      <div className="vhead">
        <span className="vbadge">
          <Icon id="i-check" />
          Transfer verified
        </span>
        <span className="pillbtn">
          <b>0 hints</b> on the fresh problem
        </span>
      </div>
      <h2>
        Both learners <em>just learned.</em>
      </h2>
      <p className="lede" style={{ marginBottom: 18 }}>One verified moment updates what Cognify knows about you, and what it knows about how to teach you.</p>
      <div className="rewards">
        <div className="reward">
          <Icon id="i-flame" />
          <span><b>{BASE.streak + 1}-day streak</b> · come back tomorrow</span>
        </div>
        <div className="reward">
          <Icon id="i-book" />
          <span><b>New book on your shelf</b> · Quadratic modelling</span>
        </div>
        <div className="reward">
          <Icon id="i-check" />
          <span><b>Independence</b> · 4 hints → 0</span>
        </div>
      </div>
      <div className="twin">
        <div className="paper">
          <div className="side-title">
            <h3>What you understand</h3>
            <span className="kicker">Quadratic modelling</span>
          </div>
          <ul className="ladder">
            {LADDER.map((l, i) => {
              const s = flipped[i] ? l[3] : l[2];
              return (
                <li key={l[0]} data-i={i} data-s={s} className={flipped[i] ? "flip" : undefined}>
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
          <div className="twin-note">Every label is backed by a specific attempt, not an unexplained percentage.</div>
        </div>
        <div className="paper">
          <div className="side-title">
            <h3>How Cognify teaches you</h3>
            <span className="pill seed">Seeded history</span>
          </div>
          <div>
            <span className="kicker">Visual + Socratic · words → equation</span>
            <div className="odo">
              <span className="v">{odoStep >= 1 ? after.independent_successes : before.independent_successes}</span>
              <small>/</small>
              <span className="v">{odoStep >= 2 ? after.uses : before.uses}</span>
              <small>independent</small>
              <span className="was">{odoStep >= 3 ? `was ${before.independent_successes} / ${before.uses}` : ""}</span>
            </div>
          </div>
          <div className="spark">
            <span className="kicker">Hints needed over time</span>
            <div>
              <Spark key={vals.length} vals={vals} labels={labels} animate={fullSpark} />
            </div>
          </div>
          <div className="twin-note">Next time this gap shows up, the strategy that worked starts with stronger evidence.</div>
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
      </div>
    </section>
  );
}
