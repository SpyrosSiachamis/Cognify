"use client";

import { useRef, type KeyboardEvent } from "react";
import { DEMO_PROBLEM, type Mode } from "@/lib/state";
import { useApp } from "./AppProvider";
import { Icon } from "./Icons";
import { Shelf } from "./Shelf";

const LEVELS: { id: Mode; level: string; name: string; icon: "i-bolt" | "i-mountain"; line: string; points: string[] }[] = [
  { id: "simple", level: "Level I · about a minute", name: "Simple", icon: "i-bolt", line: "A clear answer, fast.", points: ["Step-by-step solution", "The key idea, in brief", "Not counted as progress"] },
  { id: "master", level: "Level II · about five minutes", name: "Master", icon: "i-mountain", line: "Learn it, then prove it.", points: ["Finds where you get stuck", "You build it, with small hints", "Tested on a fresh problem"] },
];

export function Home({ onStart }: { onStart: () => void }) {
  const { state, dispatch } = useApp();
  const field = useRef<HTMLTextAreaElement>(null);
  const cards = useRef<Record<Mode, HTMLButtonElement | null>>({ simple: null, master: null });

  const pick = (mode: Mode) => dispatch({ type: "mode", mode });
  const onKeys = (e: KeyboardEvent) => {
    if (!["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].includes(e.key)) return;
    e.preventDefault();
    const next: Mode = state.mode === "master" ? "simple" : "master";
    pick(next);
    cards.current[next]?.focus();
  };

  return (
    <section className="view">
      <p className="eyebrow">Welcome back, Maria</p>
      <h1>
        Solve it. Then <em>prove it.</em>
      </h1>
      <p className="lede">Paste any problem. Cognify learns how you think, teaches the way that works for you, then checks you can do the next one alone.</p>
      <div className="paper ask">
        <div className="spread">
          <h3 aria-level={2}>What are you working on?</h3>
          <button
            type="button"
            className="try"
            onClick={() => {
              dispatch({ type: "problem", problem: DEMO_PROBLEM });
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
        <div className="modes" role="radiogroup" aria-label="How deep" onKeyDown={onKeys}>
          {LEVELS.map((l) => (
            <button
              key={l.id}
              ref={(el) => {
                cards.current[l.id] = el;
              }}
              type="button"
              className="mode"
              role="radio"
              aria-checked={state.mode === l.id}
              tabIndex={state.mode === l.id ? 0 : -1}
              onClick={() => pick(l.id)}
            >
              <span className="lv">{l.level}</span>
              <span className="top2">
                <Icon id={l.icon} />
                <span className="nm">{l.name}</span>
              </span>
              <span className="mc">{l.line}</span>
              <ul>
                {l.points.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </button>
          ))}
        </div>
        <button className="btn btn-main btn-wide" type="button" onClick={onStart}>
          {state.mode === "master" ? "Start Master session" : "Show me the steps"} <Icon id="i-arrow" className="arr" />
        </button>
        <p className="demo-note">The walkthrough runs on a prepared scenario. Live AI plugs in behind the same screens.</p>
      </div>
      <Shelf />
    </section>
  );
}
