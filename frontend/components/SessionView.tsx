"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, type Solution } from "@/lib/api";
import type { Beat, MasterSession, Rich, StudentInput, Turn, TutorService, Widget } from "@/lib/tutor/types";
import type { Phase } from "@/lib/vocab";
import { useApp } from "./AppProvider";
import { EndedCard, ErrorCard, ProblemCard, ReplyCard, SolutionCard, StressCard } from "./session/Cards";
import { TutorMsg, YouMsg } from "./session/Messages";

type Item =
  | { id: number; kind: "problem"; text: string }
  | { id: number; kind: "tutor"; paragraphs: Rich[] | null } // null: Cognify is working (typing dots)
  | { id: number; kind: "you"; text: string }
  | { id: number; kind: "widget"; widget: Widget; done: boolean }
  | { id: number; kind: "error"; error: ApiError }
  | { id: number; kind: "solution"; solution: Solution };

const PHASES = ["Think", "Learn", "Prove"];
const PHASE_STEP: Record<Phase, number> = { ask_first_thought: 0, teach: 1, stress_test: 2, verdict: 2, exited: 2 };
const STOP = Symbol("session stopped");

const asApiError = (e: unknown) => (e instanceof ApiError ? e : new ApiError("unexpected", String(e), true));

/* The Master conversation. A small loop sends the student's text to the backend, plays the mapped turn
   (messages, log lines, the diagnosis for Progress…) and waits for the next answer. */
export function SessionView({ tutor, onNewProblem }: { tutor: TutorService; onNewProblem: () => void }) {
  const { state, dispatch } = useApp();
  const [items, setItems] = useState<Item[]>([]);
  const [phase, setPhase] = useState(-1);
  const [canExit, setCanExit] = useState(false);
  const waiting = useRef<((input: StudentInput) => void) | null>(null);
  const retrying = useRef<(() => void) | null>(null);
  const exitRef = useRef<(() => Promise<void>) | null>(null);
  const problem = useRef(state.problem);
  problem.current = state.problem;

  useEffect(() => {
    let stopped = false;
    let nextId = 1;
    const controller = new AbortController();
    let session: MasterSession | null = null;
    const alive = () => {
      if (stopped) throw STOP;
    };
    const log = (b: string, s?: string, k?: "" | "ok" | "ai") => dispatch({ type: "log", b, s, k, now: Date.now() });
    const add = (item: Item extends infer T ? (T extends { id: number } ? Omit<T, "id"> : never) : never) => {
      const id = nextId++;
      setItems((list) => [...list, { ...item, id } as Item]);
      return id;
    };
    const update = (id: number, change: Partial<Item>) => setItems((list) => list.map((it) => (it.id === id ? ({ ...it, ...change } as Item) : it)));
    const remove = (id: number) => setItems((list) => list.filter((it) => it.id !== id));

    function play(beats: Beat[]) {
      for (const beat of beats) {
        if ("say" in beat) add({ kind: "tutor", paragraphs: beat.say });
        else if ("log" in beat) log(beat.log.b, beat.log.s, beat.log.k);
        else if ("phase" in beat) {
          dispatch({ type: "phase", phase: beat.phase });
          setPhase(PHASE_STEP[beat.phase]);
        } else if ("diagnosis" in beat) dispatch({ type: "diagnosis", diagnosis: beat.diagnosis });
        else if ("method" in beat) dispatch({ type: "method", method: beat.method });
        else if ("hints" in beat) dispatch({ type: "hints", hints: beat.hints });
        else if ("verdict" in beat) dispatch({ type: "verdict", verdict: beat.verdict, over: beat.over });
        else if ("fresh" in beat) dispatch({ type: "fresh", on: true });
        else if ("toast" in beat) dispatch({ type: "toast", toast: beat.toast });
        else if ("dim" in beat) dispatch({ type: "dim", on: beat.dim });
        else if ("seal" in beat) dispatch({ type: "seal", open: true });
      }
    }

    /** Run one backend request with the typing dots showing. On failure: an error card and a Retry button. */
    async function withRetry<T>(request: () => Promise<T>): Promise<T> {
      for (;;) {
        const typing = add({ kind: "tutor", paragraphs: null });
        try {
          const result = await request();
          alive();
          remove(typing);
          return result;
        } catch (e) {
          alive();
          remove(typing);
          const error = asApiError(e);
          if (error.code === "cancelled") throw STOP;
          log("Request failed", error.message);
          const card = add({ kind: "error", error });
          await new Promise<void>((resolve) => (retrying.current = resolve));
          alive();
          remove(card);
        }
      }
    }

    const nextInput = () => new Promise<StudentInput>((resolve) => (waiting.current = resolve));

    exitRef.current = async () => {
      if (!session) return;
      const s = session;
      session = null;
      stopped = true; // the conversation loop stops; the exit is the last request
      controller.abort();
      waiting.current = null;
      retrying.current = null;
      setCanExit(false);
      setItems((list) => list.filter((it) => it.kind !== "widget" && !(it.kind === "tutor" && it.paragraphs === null) && it.kind !== "error"));
      try {
        const solution = await s.exit();
        dispatch({ type: "phase", phase: "exited" });
        dispatch({ type: "dim", on: false });
        log("Left the session", "Solution shown; no evidence recorded");
        setItems((list) => [...list, { id: nextId++, kind: "solution", solution }]);
      } catch (e) {
        setItems((list) => [...list, { id: nextId++, kind: "error", error: asApiError(e) }]);
      }
    };

    async function main() {
      await Promise.resolve(); // lets React's dev double-run cancel the first attempt before anything is sent
      alive();
      log("Session started", "Master level", "ai");
      setPhase(0);
      setItems([]);
      add({ kind: "problem", text: problem.current.trim() });
      const opened = await withRetry(() => tutor.begin(problem.current.trim(), controller.signal));
      session = opened.session;
      setCanExit(true);
      let turn: Turn = opened.turn;
      play(turn.beats);

      while (turn.next) {
        const widget = turn.next;
        const id = add({ kind: "widget", widget, done: false });
        if (widget.kind === "ended") {
          setCanExit(false); // the backend has closed the session; exit would be refused (409 session_over)
          return;
        }
        const input = await nextInput();
        alive();
        update(id, { done: true });
        add({ kind: "you", text: input.text });
        dispatch({ type: "sent", text: input.text, first: !!input.first });
        const current = session;
        turn = await withRetry(() => current!.send(input, controller.signal));
        play(turn.beats);
      }
      setCanExit(false);
    }

    main().catch((e) => {
      if (e !== STOP) console.error(e);
    });
    return () => {
      stopped = true;
      controller.abort();
      waiting.current = null;
      retrying.current = null;
      exitRef.current = null;
    };
  }, [state.run, tutor, dispatch]);

  const submit = (input: StudentInput) => {
    const resolve = waiting.current;
    waiting.current = null;
    resolve?.(input);
  };
  const retry = () => {
    const resolve = retrying.current;
    retrying.current = null;
    resolve?.();
  };

  return (
    <section className="view">
      <div className="spread">
        <div className="phase">
          {PHASES.map((name, i) => (
            <span key={name} className={i < phase ? "done" : i === phase ? "now" : ""}>
              {name}
            </span>
          ))}
        </div>
        {canExit && (
          <button type="button" className="btn-ghost" onClick={() => exitRef.current?.()}>
            Exit and see the solution
          </button>
        )}
      </div>
      <div className="thread" aria-live="polite" aria-busy={items.some((it) => it.kind === "tutor" && it.paragraphs === null)}>
        {items.map((item) => {
          switch (item.kind) {
            case "problem":
              return <ProblemCard key={item.id} text={item.text} />;
            case "tutor":
              return <TutorMsg key={item.id} paragraphs={item.paragraphs} />;
            case "you":
              return <YouMsg key={item.id} text={item.text} />;
            case "error":
              return <ErrorCard key={item.id} error={item.error} onRetry={item.error.retryable ? retry : undefined} />;
            case "solution":
              return <SolutionCard key={item.id} solution={item.solution} />;
            case "widget": {
              const w = item.widget;
              if (w.kind === "reply") return <ReplyCard key={item.id} widget={w} done={item.done} onSubmit={(text) => submit({ text, first: w.first })} />;
              if (w.kind === "stress") return <StressCard key={item.id} widget={w} done={item.done} onSubmit={(text) => submit({ text })} />;
              return <EndedCard key={item.id} widget={w} onNewProblem={onNewProblem} />;
            }
          }
        })}
      </div>
    </section>
  );
}
