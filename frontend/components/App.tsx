"use client";

import { useCallback, useEffect } from "react";
import { ApiError } from "@/lib/api";
import { loadViews } from "@/lib/backend";
import { backendTutor } from "@/lib/tutor/backend";
import { AppProvider, useActions, useAppSelector } from "./AppProvider";
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
  // The shell only needs these two; everything else reads its own part of the state.
  const view = useAppSelector((s) => s.view);
  const verdict = useAppSelector((s) => s.session.verdict);
  const { dispatch, getState } = useActions();

  // What the backend knows about the learner. Loading and failure are shown as they are; nothing is filled in.
  const refreshViews = useCallback(() => {
    loadViews()
      .then((data) => dispatch({ type: "views", views: { status: "ok", data } }))
      .catch((e) => dispatch({ type: "views", views: { status: "error", message: e instanceof ApiError ? e.message : String(e) } }));
  }, [dispatch]);
  useEffect(refreshViews, [refreshViews]);

  // A verdict changes the learner's concept state and strategy counts on the backend: read them again.
  useEffect(() => {
    if (verdict) refreshViews();
  }, [verdict, refreshViews]);

  // A soft light follows the pointer across the paper cards. Updated at most once per frame,
  // so fast mouse movement does not measure the page dozens of times between two frames.
  useEffect(() => {
    let last: PointerEvent | null = null;
    let frame = 0;
    const paint = () => {
      frame = 0;
      const e = last;
      if (!e) return;
      const paper = (e.target as Element | null)?.closest?.(".paper") as HTMLElement | null;
      if (!paper) return;
      const r = paper.getBoundingClientRect();
      paper.style.setProperty("--mx", e.clientX - r.left + "px");
      paper.style.setProperty("--my", e.clientY - r.top + "px");
    };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      last = e;
      if (!frame) frame = requestAnimationFrame(paint);
    };
    addEventListener("pointermove", onMove, { passive: true });
    return () => {
      removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  // Every new screen starts at the top.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [view]);

  // Stable handlers, so the memoised parts of the page do not re-render when the shell does.
  const newProblem = useCallback(() => dispatch({ type: "newProblem" }), [dispatch]);
  const start = useCallback(() => {
    if (!getState().problem.trim()) return;
    dispatch({ type: "startSession", now: Date.now() });
  }, [dispatch, getState]);
  // From the seal to the result screen.
  const showResult = useCallback(() => {
    dispatch({ type: "seal", open: false });
    dispatch({ type: "view", view: "result" });
  }, [dispatch]);

  return (
    <>
      <IconSprite />
      <Room />
      <TopBar onNewProblem={newProblem} />
      <main className="wrap" id="main">
        {view === "home" && <Home onStart={start} onRetryViews={refreshViews} />}
        {view === "session" && <SessionView tutor={backendTutor} onNewProblem={newProblem} />}
        {view === "result" && <ResultView onNewProblem={newProblem} />}
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
