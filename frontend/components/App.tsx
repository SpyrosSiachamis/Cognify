"use client";

import { useCallback, useEffect } from "react";
import { ApiError } from "@/lib/api";
import { loadViews } from "@/lib/backend";
import { backendTutor } from "@/lib/tutor/backend";
import { AppProvider, useApp } from "./AppProvider";
import { Home } from "./Home";
import { IconSprite } from "./Icons";
import { ProgressDrawer } from "./ProgressDrawer";
import { ResultView } from "./ResultView";
import { SealOverlay } from "./SealOverlay";
import { SessionView } from "./SessionView";
import { Toast } from "./Toast";
import { Room } from "./Room";
import { TopBar } from "./TopBar";

function Shell() {
  const { state, dispatch } = useApp();

  // What the backend knows about the learner. Loading and failure are shown as they are; nothing is filled in.
  const refreshViews = useCallback(() => {
    loadViews()
      .then((data) => dispatch({ type: "views", views: { status: "ok", data } }))
      .catch((e) => dispatch({ type: "views", views: { status: "error", message: e instanceof ApiError ? e.message : String(e) } }));
  }, [dispatch]);
  useEffect(refreshViews, [refreshViews]);

  // A verdict changes the learner's concept state and strategy counts on the backend: read them again.
  const verdict = state.session.verdict;
  useEffect(() => {
    if (verdict) refreshViews();
  }, [verdict, refreshViews]);

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

  // Every new screen starts at the top.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [state.view]);

  const newProblem = () => dispatch({ type: "newProblem" });
  const start = () => {
    if (!state.problem.trim()) return;
    dispatch({ type: "startSession", now: Date.now() });
  };
  // From the seal to the result screen.
  const showResult = () => {
    dispatch({ type: "seal", open: false });
    dispatch({ type: "view", view: "result" });
  };

  return (
    <>
      <IconSprite />
      <Room />
      <TopBar onNewProblem={newProblem} />
      <main className="wrap" id="main">
        {state.view === "home" && <Home onStart={start} onRetryViews={refreshViews} />}
        {state.view === "session" && <SessionView tutor={backendTutor} onNewProblem={newProblem} />}
        {state.view === "result" && <ResultView onNewProblem={newProblem} />}
      </main>
      <ProgressDrawer onRefresh={refreshViews} />
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
