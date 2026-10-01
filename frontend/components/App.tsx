"use client";

import { useEffect, useState } from "react";
import { DEMO_PROBLEM } from "@/lib/state";
import { scriptedTutor } from "@/lib/tutor/scripted";
import type { Answer } from "@/lib/tutor/types";
import { AppProvider, useApp } from "./AppProvider";
import { Home } from "./Home";
import { IconSprite } from "./Icons";
import { QuickView } from "./QuickView";
import { Room } from "./Room";
import { TopBar } from "./TopBar";

// The tutor behind the screens. Swap this one line to plug in the real backend.
const tutor = scriptedTutor;

function Shell() {
  const { state, dispatch } = useApp();
  const [answer, setAnswer] = useState<Answer | null>(null);

  // Every new screen starts at the top, like the prototype.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [state.view]);

  const newProblem = () => {
    if (state.sealOpen) return;
    dispatch({ type: "newProblem" });
  };
  const startMaster = () => {
    dispatch({ type: "mode", mode: "master" });
    dispatch({ type: "startSession", now: Date.now() });
  };
  const start = async () => {
    // An empty box falls back to the example problem, like the prototype.
    const problem = state.problem.trim() ? state.problem : DEMO_PROBLEM;
    if (problem !== state.problem) dispatch({ type: "problem", problem });
    if (state.mode === "master") return startMaster();
    setAnswer(await tutor.answer(problem));
    dispatch({ type: "view", view: "quick" });
  };

  return (
    <>
      <IconSprite />
      <Room />
      <TopBar onNewProblem={newProblem} />
      <main className="wrap" id="main">
        {state.view === "home" && <Home onStart={start} />}
        {state.view === "quick" && answer && <QuickView answer={answer} onMaster={startMaster} onBack={newProblem} />}
      </main>
    </>
  );
}

export function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
