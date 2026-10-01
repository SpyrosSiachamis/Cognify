"use client";

import { useEffect, useRef, useState } from "react";
import { sleep } from "@/lib/fx";
import { htmlLength } from "@/lib/tutor/rich";
import type { Beat, Rich, StudentInput, Turn, TutorService, Widget } from "@/lib/tutor/types";
import { useApp } from "./AppProvider";
import { BuiltCard, IdeaCard, ProbeCard, ProblemCard, QuestionCard, ReadyCard, TransferCard } from "./session/Cards";
import { TutorMsg, YouMsg } from "./session/Messages";

type Feedback = { tone: "good" | "nudge"; text: string } | undefined;
type Item =
  | { id: number; kind: "problem"; text: string }
  | { id: number; kind: "tutor"; paragraphs: Rich[] | null }
  | { id: number; kind: "you"; text: string }
  | { id: number; kind: "widget"; widget: Widget; done: boolean; feedback: Feedback; misses: number }
  | { id: number; kind: "built"; equation: string; summary: Rich };

const PHASES = ["Think", "Learn", "Prove"];
const STOP = Symbol("session stopped");

/* The Master conversation. A small loop asks the tutor for the next turn, plays its beats
   (messages, log lines, toasts…) and then waits for the student to answer the next question. */
export function SessionView({ tutor }: { tutor: TutorService }) {
  const { state, dispatch } = useApp();
  const [items, setItems] = useState<Item[]>([]);
  const [phase, setPhase] = useState(-1);
  const waiting = useRef<((input: StudentInput) => void) | null>(null);
  const problem = useRef(state.problem);
  problem.current = state.problem;

  useEffect(() => {
    let stopped = false;
    let nextId = 1;
    const alive = () => {
      if (stopped) throw STOP;
    };
    const log = (b: string, s?: string, k?: "" | "ok" | "ai") => dispatch({ type: "log", b, s, k, now: Date.now() });
    const add = (item: Item extends infer T ? (T extends { id: number } ? Omit<T, "id"> : never) : never) => {
      const id = nextId++;
      setItems((list) => [...list, { ...item, id } as Item]);
      return id;
    };
    const update = (id: number, patch: Partial<Item>) => setItems((list) => list.map((it) => (it.id === id ? ({ ...it, ...patch } as Item) : it)));
    const remove = (id: number) => setItems((list) => list.filter((it) => it.id !== id));

    async function say(paragraphs: Rich[]) {
      const id = add({ kind: "tutor", paragraphs: null });
      await sleep(500 + Math.min(htmlLength(paragraphs) * 3, 700));
      alive();
      update(id, { paragraphs });
    }

    async function play(beats: Beat[]) {
      for (const beat of beats) {
        alive();
        if ("say" in beat) await say(beat.say);
        else if ("log" in beat) log(beat.log.b, beat.log.s, beat.log.k);
        else if ("mark" in beat) dispatch(beat.mark === "shared" ? { type: "shared", thought: beat.thought } : { type: "probed" });
        else if ("fresh" in beat) dispatch({ type: "fresh", on: true });
        else if ("toast" in beat) dispatch({ type: "toast", toast: beat.toast });
        else if ("phase" in beat) setPhase(beat.phase);
        else if ("dim" in beat) dispatch({ type: "dim", on: beat.dim });
        else if ("built" in beat) add({ kind: "built", equation: beat.built.equation, summary: beat.built.summary });
        else if ("pause" in beat) await sleep(beat.pause);
        else if ("seal" in beat) {
          log("Transfer verified", "Fresh problem solved with 0 hints", "ok");
          dispatch({ type: "verified" });
          dispatch({ type: "fresh", on: true });
          dispatch({ type: "dim", on: false });
          dispatch({ type: "seal", open: true });
        }
      }
    }

    const nextInput = () => new Promise<StudentInput>((resolve) => (waiting.current = resolve));

    async function main() {
      await Promise.resolve(); // lets React's dev double-run cancel the first attempt before anything is logged
      alive();
      log("Session started", "Master level", "ai");
      setPhase(0);
      setItems([]);
      add({ kind: "problem", text: problem.current.trim() });
      await sleep(450);
      alive();
      const { session, turn: opening } = await tutor.begin(problem.current.trim());
      alive();
      let turn: Turn = opening;
      await play(turn.beats);

      while (turn.next) {
        const widget = turn.next;
        const id = add({ kind: "widget", widget, done: false, feedback: undefined, misses: 0 });
        let accepted: Turn;
        let misses = 0;
        for (;;) {
          const input = await nextInput();
          alive();
          // The idea and the warm-up show up as the student's own message right away.
          if (widget.kind === "idea") {
            remove(id);
            add({ kind: "you", text: input.text });
          } else if (widget.kind === "probe") {
            update(id, { done: true });
            add({ kind: "you", text: input.text });
          } else if (widget.kind === "ready") {
            remove(id);
          }
          const reply = await session.send(input);
          alive();
          if (reply.accepted) {
            accepted = reply;
            break;
          }
          misses += 1;
          update(id, { feedback: reply.feedback, misses });
        }
        if (widget.kind === "question") update(id, { done: true, feedback: accepted.feedback });
        await play(accepted.beats);
        turn = accepted;
      }
    }

    main().catch((e) => {
      if (e !== STOP) console.error(e);
    });
    return () => {
      stopped = true;
      waiting.current = null;
    };
  }, [state.run, tutor, dispatch]);

  const submit = (input: StudentInput) => {
    const resolve = waiting.current;
    waiting.current = null;
    resolve?.(input);
  };

  return (
    <section className="view">
      <div className="phase">
        {PHASES.map((name, i) => (
          <span key={name} className={i < phase ? "done" : i === phase ? "now" : ""}>
            {name}
          </span>
        ))}
      </div>
      <div className="thread" aria-live="polite">
        {items.map((item) => {
          switch (item.kind) {
            case "problem":
              return <ProblemCard key={item.id} text={item.text} />;
            case "tutor":
              return <TutorMsg key={item.id} paragraphs={item.paragraphs} />;
            case "you":
              return <YouMsg key={item.id} text={item.text} />;
            case "built":
              return <BuiltCard key={item.id} equation={item.equation} summary={item.summary} />;
            case "widget": {
              const w = item.widget;
              if (w.kind === "idea") return <IdeaCard key={item.id} widget={w} onSubmit={(text) => submit({ text, kind: "idea" })} />;
              if (w.kind === "probe") return <ProbeCard key={item.id} widget={w} done={item.done} onSubmit={(text) => submit({ text, kind: "probe" })} />;
              if (w.kind === "question") return <QuestionCard key={item.id} widget={w} done={item.done} feedback={item.feedback} onSubmit={(text) => submit({ text, kind: "question" })} />;
              if (w.kind === "ready") return <ReadyCard key={item.id} widget={w} onSubmit={() => submit({ text: "", kind: "ready" })} />;
              return <TransferCard key={item.id} widget={w} misses={item.misses} onSubmit={(text, answer) => submit({ text, answer, kind: "transfer" })} />;
            }
          }
        })}
      </div>
    </section>
  );
}
