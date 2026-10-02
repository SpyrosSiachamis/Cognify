"use client";

import { useRef } from "react";
import { EXAMPLE_PROBLEM } from "@/lib/state";
import { useApp } from "./AppProvider";
import { Icon } from "./Icons";
import { Shelf } from "./Shelf";

export function Home({ onStart, onRetryViews }: { onStart: () => void; onRetryViews: () => void }) {
  const { state, dispatch, replay } = useApp();
  const field = useRef<HTMLTextAreaElement>(null);
  const views = state.views;
  const name = views.status === "ok" ? views.data.learner.display_name : null;
  const ready = state.problem.trim().length > 0;

  return (
    <section className="view">
      <p className="eyebrow">{name ? `Welcome back, ${name}` : "Welcome back"}</p>
      <h1>
        Solve it. Then <em>prove it.</em>
      </h1>
      <p className="lede">Paste any problem. Cognify reads how you think, teaches the way that has worked for you, then checks you can do the next one alone.</p>
      <div className="paper ask">
        <div className="spread">
          <h3 aria-level={2}>What are you working on?</h3>
          <button
            type="button"
            className="try"
            onClick={() => {
              dispatch({ type: "problem", problem: EXAMPLE_PROBLEM });
              field.current?.focus();
            }}
          >
            <Icon id="i-spark" />
            Try an example
          </button>
        </div>
        <div className="fieldwrap">
          <textarea
            ref={field}
            className="field"
            rows={3}
            maxLength={2000}
            aria-label="Your problem"
            placeholder="Paste or type a problem…"
            value={state.problem}
            onChange={(e) => dispatch({ type: "problem", problem: e.target.value })}
          />
          <span className="count counter">{state.problem.length} / 2000</span>
        </div>
        <div className="modes" role="radiogroup" aria-label="How deep">
          <button type="button" className="mode" role="radio" aria-checked={false} aria-disabled="true" tabIndex={-1} disabled>
            <span className="lv">Level I · not available yet</span>
            <span className="top2">
              <Icon id="i-bolt" />
              <span className="nm">Simple</span>
            </span>
            <span className="mc">A clear answer, fast.</span>
            <ul>
              <li>The backend does not serve Level I answers yet</li>
            </ul>
          </button>
          <button type="button" className="mode" role="radio" aria-checked tabIndex={0}>
            <span className="lv">Level II · Master</span>
            <span className="top2">
              <Icon id="i-mountain" />
              <span className="nm">Master</span>
            </span>
            <span className="mc">Learn it, then prove it.</span>
            <ul>
              <li>Finds where you get stuck</li>
              <li>You build it, with small hints</li>
              <li>Tested on a fresh problem</li>
            </ul>
          </button>
        </div>
        <button className="btn btn-main btn-wide" type="button" onClick={onStart} disabled={!ready}>
          Start Master session <Icon id="i-arrow" className="arr" />
        </button>
        <p className="demo-note">
          {replay}
          {!replay && views.status === "ok" && "Connected to Cognify. Every reply comes from the live tutor."}
          {!replay && views.status === "loading" && "Connecting to Cognify…"}
          {views.status === "error" && (
            <>
              Cannot reach Cognify: {views.message}{" "}
              <button type="button" className="link" onClick={onRetryViews}>
                Try again
              </button>
            </>
          )}
        </p>
      </div>
      <Shelf />
    </section>
  );
}
