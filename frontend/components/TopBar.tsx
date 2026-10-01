"use client";

import { BASE, type Theme } from "@/lib/state";
import { useApp } from "./AppProvider";
import { Icon } from "./Icons";

const THEMES: { id: Theme; label: string }[] = [
  { id: "velvet", label: "Velvet" },
  { id: "salon", label: "Salon" },
];

export function TopBar({ onNewProblem }: { onNewProblem: () => void }) {
  const { state, dispatch, chooseTheme } = useApp();
  const streak = BASE.streak + (state.bumped ? 1 : 0);
  const proven = BASE.proven + (state.bumped ? 1 : 0);

  return (
    <header className="bar">
      <button className="brand" type="button" onClick={onNewProblem} aria-label="Cognify home">
        <svg viewBox="0 0 56 56" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M7 35c9-3.400 16-2.600 21 2.400 5-5 12-5.800 21-2.400v9.500c-9-3.200-16-2.400-21 2.800-5-5.200-12-6-21-2.800z" />
          <path d="M28 37.400v9.800" />
          <path d="M28 34C22 28 22 20 28 9c6 11 6 19 0 25z" />
          <path d="M25.500 34c-7-2.500-11-8.500-11-16 7 1.800 10.500 7.500 11 16z" />
          <path d="M30.500 34c7-2.500 11-8.500 11-16-7 1.800-10.500 7.500-11 16z" />
          <circle cx="28" cy="9" r="1.600" fill="currentColor" />
        </svg>
        <b>Cognify</b>
      </button>
      <div className="bar-r">
        <span className="pillbtn" id="streak" title="Daily streak">
          <Icon id="i-flame" className="lamp-lit" />
          <b>{streak}</b>
          <span className="hide-m">day streak</span>
        </span>
        <span className="pillbtn hide-s" id="vchip" title="Concepts you have proven">
          <Icon id="i-check" />
          <b>{proven}</b> proven
        </span>
        <div className="seg" role="group" aria-label="Colour theme">
          {THEMES.map((t) => (
            <button key={t.id} type="button" aria-pressed={state.theme === t.id} onClick={() => chooseTheme(t.id)}>
              <i className={`sw-${t.id}`} />
              <span>{t.label}</span>
            </button>
          ))}
        </div>
        <button className="pillbtn hide-s" type="button" onClick={onNewProblem}>
          <Icon id="i-pencil" />
          New problem
        </button>
        <button
          className={`btn-progress${state.fresh ? " news" : ""}`}
          type="button"
          aria-haspopup="dialog"
          onClick={() => dispatch({ type: "sheet", open: true })}
        >
          <Icon id="i-chart" />
          <span>Progress</span>
          <i className="dot" />
        </button>
      </div>
    </header>
  );
}
