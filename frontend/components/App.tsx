"use client";

import { useCallback, useEffect, useMemo } from "react";
import { ApiError } from "@/lib/api";
import { loadViews } from "@/lib/backend";
import { buildRecording, createRecorder, saveRecording } from "@/lib/tutor/recorder";
import { replay, type Recording } from "@/lib/tutor/replay";
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

function Shell({ recording }: { recording?: Recording }) {
  // The shell only needs these two; everything else reads its own part of the state.
  const view = useAppSelector((s) => s.view);
  const verdict = useAppSelector((s) => s.session.verdict);
  const { dispatch, getState } = useActions();
  // A replay plays a recorded session through the same screens; nothing calls the backend.
  const player = useMemo(() => (recording ? replay(recording) : null), [recording]);
  // The live tutor records each session, so a finished one can be saved as a replay (lib/tutor/recorder.ts).
  const recorder = useMemo(() => createRecorder(() => {
    const views = getState().views;
    return views.status === "ok" ? views.data : null;
  }), [getState]);
  const tutor = player?.tutor ?? recorder.tutor;
  const load = player?.loadViews ?? loadViews;

  // What the backend knows about the learner. Loading and failure are shown as they are; nothing is filled in.
  const refreshViews = useCallback(() => {
    load()
      .then((data) => dispatch({ type: "views", views: { status: "ok", data } }))
      .catch((e) => dispatch({ type: "views", views: { status: "error", message: e instanceof ApiError ? e.message : String(e) } }));
  }, [dispatch, load]);
  useEffect(refreshViews, [refreshViews]);

  // A replay starts from its recorded problem. Read with getState, so typing in the box does not re-render the shell.
  useEffect(() => {
    if (recording && view === "home" && !getState().problem) dispatch({ type: "problem", problem: recording.problem });
  }, [recording, view, getState, dispatch]);

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
  // Save the session just played as a replay in this browser. Returns it, and whether the browser stored it.
  const saveReplay = useCallback(async () => {
    const draft = recorder.current();
    if (!draft) throw new Error("There is no recorded session to save.");
    const views = getState().views;
    const recording = await buildRecording(draft, views.status === "ok" ? views.data : null);
    return { recording, stored: saveRecording(recording) };
  }, [recorder, getState]);
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
        {view === "session" && <SessionView tutor={tutor} onNewProblem={newProblem} />}
        {view === "result" && <ResultView onNewProblem={newProblem} onSaveReplay={player ? undefined : saveReplay} />}
      </main>
      <ProgressDrawer onRefresh={refreshViews} />
      <Toast />
      <SealOverlay onContinue={showResult} />
    </>
  );
}

export function App({ recording }: { recording?: Recording } = {}) {
  return (
    <AppProvider replay={recording?.label ?? null}>
      <Shell recording={recording} />
    </AppProvider>
  );
}
