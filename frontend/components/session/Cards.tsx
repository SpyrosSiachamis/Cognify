"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { lookAt, popAt } from "@/lib/fx";
import type { Rich, Widget } from "@/lib/tutor/types";
import { useApp } from "../AppProvider";
import { Icon } from "../Icons";
import { RichText } from "../RichText";
import { RectDiagram } from "./RectDiagram";

type Feedback = { tone: "good" | "nudge"; text: string } | undefined;

// Scroll the new card into view and put the cursor in its field once it has settled.
function useEntry<T extends HTMLElement>(focusDelay: number) {
  const card = useRef<HTMLDivElement>(null);
  const field = useRef<T>(null);
  useEffect(() => {
    lookAt(card.current, "start");
    const t = setTimeout(() => field.current?.focus({ preventScroll: true }), focusDelay);
    return () => clearTimeout(t);
  }, [focusDelay]);
  return { card, field };
}

export function ProblemCard({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => lookAt(ref.current, "start"), []);
  return (
    <div className="icard prob-card" ref={ref}>
      <div className="paper">
        <span className="kicker">Your problem</span>
        <p>{text}</p>
      </div>
    </div>
  );
}

export function IdeaCard({ widget, onSubmit }: { widget: Extract<Widget, { kind: "idea" }>; onSubmit: (text: string) => void }) {
  const { card, field } = useEntry<HTMLTextAreaElement>(400);
  const [value, setValue] = useState("");
  const send = () => onSubmit(value.trim() || widget.demo);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };
  return (
    <div className="icard" ref={card}>
      <div className="paper stack">
        <textarea ref={field} className="field serif" rows={3} placeholder={widget.placeholder} aria-label="Your first idea" value={value} onChange={(e) => setValue(e.target.value)} onKeyDown={onKey} />
        <div className="spread">
          <button type="button" className="try" onClick={() => { setValue(widget.demo); field.current?.focus(); }}>
            <Icon id="i-spark" />
            Use the demo answer
          </button>
          <button className="btn btn-main" type="button" onClick={send}>
            Send <Icon id="i-arrow" className="arr" />
          </button>
        </div>
      </div>
    </div>
  );
}

export function ProbeCard({ widget, done, onSubmit }: { widget: Extract<Widget, { kind: "probe" }>; done: boolean; onSubmit: (text: string) => void }) {
  const { card, field } = useEntry<HTMLInputElement>(400);
  const [value, setValue] = useState("");
  const go = (text?: string) => onSubmit((text ?? value).trim() || widget.demo);
  return (
    <div className="icard" ref={card}>
      <div className={`paper stack${done ? " card-done" : ""}`}>
        <span className="kicker">{widget.kicker}</span>
        <p className="q">
          <RichText value={widget.prompt} />
        </p>
        <div className="inrow">
          <input
            ref={field}
            className="field mono"
            placeholder={widget.placeholder}
            aria-label={widget.ariaLabel}
            autoComplete="off"
            value={value}
            disabled={done}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && go()}
          />
          <button className="btn btn-main" type="button" onClick={() => go()}>Check</button>
        </div>
        <div className="row">
          <button type="button" className="try" onClick={() => { setValue(widget.demo); go(widget.demo); }}>
            <Icon id="i-spark" />
            Use demo answer
          </button>
        </div>
      </div>
    </div>
  );
}

export function QuestionCard({
  widget,
  done,
  feedback,
  onSubmit,
}: {
  widget: Extract<Widget, { kind: "question" }>;
  done: boolean;
  feedback: Feedback;
  onSubmit: (text: string) => void;
}) {
  const { state, dispatch } = useApp();
  const { card, field } = useEntry<HTMLInputElement>(400);
  const fb = useRef<HTMLDivElement>(null);
  const [value, setValue] = useState("");
  const [hintShown, setHintShown] = useState(false);

  // A small celebration the moment the answer is accepted.
  useEffect(() => {
    if (done) popAt(fb.current);
  }, [done]);

  const askHint = () => {
    if (hintShown) return;
    setHintShown(true);
    dispatch({ type: "hint" });
    dispatch({ type: "log", b: "Asked for a hint", s: `Hint ${state.hints + 1}`, now: Date.now() });
  };
  const stage = (done ? widget.stage + 1 : widget.stage) as 0 | 1 | 2;
  return (
    <div className="icard" ref={card}>
      <div className={`paper${done ? " card-done" : ""}`}>
        <div className="qgrid">
          <div className="stack">
            <span className="kicker">{widget.kicker}</span>
            <p className="q">
              <RichText value={widget.prompt} />
            </p>
            <div className="inrow">
              <input
                ref={field}
                className="field mono"
                placeholder={widget.placeholder}
                aria-label={widget.ariaLabel}
                autoComplete="off"
                value={value}
                disabled={done}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && onSubmit(value)}
              />
              <button className="btn btn-main" type="button" onClick={() => onSubmit(value)}>Check</button>
            </div>
            <div className={`fb${feedback ? " " + feedback.tone : ""}`} aria-live="polite" ref={fb}>
              {feedback?.text}
            </div>
            <div className={`hint${hintShown ? " show" : ""}`}>
              <RichText value={widget.hint} />
            </div>
            <div className="row">
              <button type="button" className="try" onClick={askHint}>
                <Icon id="i-bulb" />
                Need a hint
              </button>
              <button type="button" className="try" onClick={() => { setValue(widget.demo); onSubmit(widget.demo); }}>
                <Icon id="i-spark" />
                Use demo answer
              </button>
            </div>
          </div>
          <RectDiagram stage={stage} />
        </div>
      </div>
    </div>
  );
}

export function BuiltCard({ equation, summary }: { equation: string; summary: Rich }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    lookAt(ref.current, "start");
    popAt(ref.current);
  }, []);
  return (
    <div className="icard" ref={ref}>
      <div className="paper stack">
        <span className="kicker">You built it</span>
        <div>
          <span className="mathbox">{equation}</span>
        </div>
        <p className="muted" style={{ margin: 0, fontFamily: "var(--f-voice)", fontSize: 18 }}>
          <RichText value={summary} />
        </p>
      </div>
    </div>
  );
}

export function ReadyCard({ widget, onSubmit }: { widget: Extract<Widget, { kind: "ready" }>; onSubmit: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => lookAt(ref.current, "start"), []);
  return (
    <div className="icard" ref={ref}>
      <div className="paper">
        <button className="btn btn-main btn-wide" type="button" onClick={onSubmit}>
          {widget.label} <Icon id="i-arrow" className="arr" />
        </button>
      </div>
    </div>
  );
}

export function TransferCard({
  widget,
  misses,
  onSubmit,
}: {
  widget: Extract<Widget, { kind: "transfer" }>;
  misses: number;
  onSubmit: (equation: string, answer: string) => void;
}) {
  const { card, field } = useEntry<HTMLInputElement>(700);
  const paper = useRef<HTMLDivElement>(null);
  const [equation, setEquation] = useState("");
  const [answer, setAnswer] = useState("");

  // Shake the card each time the answer is not right yet.
  useEffect(() => {
    const el = paper.current;
    if (!el || misses === 0) return;
    el.classList.remove("shake");
    void el.offsetWidth;
    el.classList.add("shake");
  }, [misses]);

  return (
    <div className="icard" ref={card}>
      <div className="paper stark stack" ref={paper}>
        <span className="kicker">{widget.kicker}</span>
        <p className="fresh">
          <RichText value={widget.problem} />
        </p>
        <div className="stress-grid">
          <label>
            Your equation
            <input ref={field} className="field mono" placeholder="write the model" aria-label="Your equation" autoComplete="off" value={equation} onChange={(e) => setEquation(e.target.value)} />
          </label>
          <label>
            Smaller number
            <input
              className="field mono"
              inputMode="numeric"
              placeholder="?"
              aria-label="Your answer"
              autoComplete="off"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSubmit(equation, answer)}
            />
          </label>
        </div>
        <div className={`notyet${misses > 0 ? " show" : ""}`}>
          <RichText value={widget.notYet} />
        </div>
        <div className="spread">
          <span className="locked-help">
            <Icon id="i-lock" />
            Hints are off
          </span>
          <div className="row">
            <button type="button" className="try" onClick={() => { setEquation(widget.demoEquation); setAnswer(widget.demoAnswer); }}>
              <Icon id="i-spark" />
              Use demo answer
            </button>
            <button className="btn btn-main" type="button" onClick={() => onSubmit(equation, answer)}>
              Submit <Icon id="i-arrow" className="arr" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
