"use client";

import { useEffect, useMemo, useState } from "react";
import { DEMO_PROBLEM } from "@/lib/state";
import { loadBackendData, recordedTutor } from "@/lib/backend";
import { scriptedTutor } from "@/lib/tutor/scripted";
import type { Answer } from "@/lib/tutor/types";
import { AppProvider, useApp } from "./AppProvider";
import { Home } from "./Home";
import { IconSprite } from "./Icons";
import { ProgressDrawer } from "./ProgressDrawer";
import { QuickView } from "./QuickView";
import { ResultView } from "./ResultView";
import { SealOverlay } from "./SealOverlay";
import { SessionView } from "./SessionView";
import { Toast } from "./Toast";
import { Room } from "./Room";
import { TopBar } from "./TopBar";

// The tutor behind the screens. Swap `scriptedTutor` for the real backend tutor when it exists.
const baseTutor = scriptedTutor;

function Shell() {
  const { state, dispatch } = useApp();
  const [answer, setAnswer] = useState<Answer | null>(null);

  // Read what the backend knows about the learner. If it cannot be reached we keep the seeded history.
  const refreshBackend = () => {
    loadBackendData().then((data) => dispatch({ type: "backend", data }));
  };
  useEffect(() => {
    loadBackendData().then((data) => dispatch({ type: "backend", data }));
  }, [dispatch]);

  // The Master session is also recorded on the backend; when it verifies the fresh problem we re-read the views.
  const tutor = useMemo(
    () =>
      recordedTutor(baseTutor, (changes) => {
        dispatch({ type: "verdict", changes });
        loadBackendData().then((data) => data && dispatch({ type: "backend", data }));
      }),
    [dispatch],
  );

  // A soft light follows the pointer across the paper cards.
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      const paper = (e.target as Element | null)?.closest?.(".paper") as HTMLElement | null;
      if (!paper) return;
      const r = paper.getBoundingClientRect();
      paper.style.setProperty("--mx", e.clientX - r.left + "px");
      paper.style.setProperty("--my", e.clientY - r.top + "px");
    };
    addEventListener("pointermove", onMove, { passive: true });
    return () => removeEventListener("pointermove", onMove);
  }, []);

  // Every new screen starts at the top, like the prototype.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [state.view]);

  const newProblem = () => {
    if (state.sealOpen) return;
    dispatch({ type: "newProblem" });
  };
  // "Reset demo": forget today's session and go back to the starting history.
  const fullReset = () => {
    dispatch({ type: "sheet", open: false });
    dispatch({ type: "fullReset" });
    refreshBackend();
  };

  // From the seal to the result screen: count today's win in the top bar.
  const showResult = () => {
    dispatch({ type: "seal", open: false });
    dispatch({ type: "bump" });
    dispatch({ type: "view", view: "result" });
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
        {state.view === "session" && <SessionView tutor={tutor} />}
        {state.view === "result" && <ResultView onNewProblem={newProblem} />}
      </main>
      <ProgressDrawer onReset={fullReset} />
      <Toast />
      <SealOverlay onContinue={showResult} />
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
