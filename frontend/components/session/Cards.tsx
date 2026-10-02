"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { ApiError, Solution } from "@/lib/api";
import { lookAt } from "@/lib/fx";
import { friendlyError } from "@/lib/messages";
import type { Widget } from "@/lib/tutor/types";
import { Icon } from "../Icons";

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

/** A text box for the student's answer. Once sent it stays visible but locked (the request is in flight or done). */
function AnswerBox({ placeholder, label, done, onSubmit, focusDelay }: { placeholder: string; label: string; done: boolean; onSubmit: (text: string) => void; focusDelay: number }) {
  const { field } = useEntry<HTMLTextAreaElement>(focusDelay);
  const [value, setValue] = useState("");
  const send = () => {
    if (done || !value.trim()) return; // nothing to send; a sent answer cannot be sent twice
    onSubmit(value.trim());
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };
  return (
    <>
      <textarea ref={field} className="field serif" rows={3} maxLength={2000} placeholder={placeholder} aria-label={label} value={value} disabled={done} onChange={(e) => setValue(e.target.value)} onKeyDown={onKey} />
      <div className="spread">
        <span className="muted" style={{ fontSize: 13 }}>Enter to send · Shift+Enter for a new line</span>
        <button className="btn btn-main" type="button" onClick={send} disabled={done || !value.trim()}>
          Send <Icon id="i-arrow" className="arr" />
        </button>
      </div>
    </>
  );
}

export function ReplyCard({ widget, done, onSubmit }: { widget: Extract<Widget, { kind: "reply" }>; done: boolean; onSubmit: (text: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => lookAt(ref.current, "start"), []);
  if (done) return null; // the sent text now shows as the student's message
  return (
    <div className="icard" ref={ref}>
      <div className="paper stack">
        <span className="kicker">{widget.kicker}</span>
        <AnswerBox placeholder={widget.placeholder} label={widget.kicker} done={done} onSubmit={onSubmit} focusDelay={400} />
      </div>
    </div>
  );
}

export function StressCard({ widget, done, onSubmit }: { widget: Extract<Widget, { kind: "stress" }>; done: boolean; onSubmit: (text: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => lookAt(ref.current, "start"), []);
  return (
    <div className="icard" ref={ref}>
      <div className={`paper stark stack${done ? " card-done" : ""}`}>
        <span className="kicker">{widget.kicker}</span>
        <p className="fresh">{widget.problem}</p>
        {!done && <AnswerBox placeholder={widget.placeholder} label="Your solution" done={done} onSubmit={onSubmit} focusDelay={700} />}
        <span className="locked-help">
          <Icon id="i-lock" />
          Hints are off
        </span>
      </div>
    </div>
  );
}

export function ErrorCard({ error, onRetry, onRestart }: { error: ApiError; onRetry?: () => void; onRestart?: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => lookAt(ref.current, "start"), []);
  return (
    <div className="icard" ref={ref} role="alert">
      <div className="paper stack">
        <div className="notyet show">
          <b>{friendlyError(error.code)}</b>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>
          {error.status ? `${error.code} · ${error.status}` : error.code}
        </p>
        {onRetry ? (
          <div className="row">
            <button className="btn btn-main" type="button" onClick={onRetry}>
              Try again <Icon id="i-arrow" className="arr" />
            </button>
          </div>
        ) : error.code === "unknown_session" && onRestart ? (
          // The backend restarted and forgot this session: start the same problem again in one click.
          <div className="row">
            <button className="btn btn-main" type="button" onClick={onRestart}>
              Start this problem again <Icon id="i-arrow" className="arr" />
            </button>
          </div>
        ) : (
          <p className="muted" style={{ margin: 0 }}>This cannot be retried. Start a new problem to continue.</p>
        )}
      </div>
    </div>
  );
}

export function SolutionCard({ solution }: { solution: Solution }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => lookAt(ref.current, "start"), []);
  return (
    <div className="icard" ref={ref}>
      <div className="paper stack">
        <span className="kicker">The solution</span>
        <div className="result">
          <span className="ic">
            <Icon id="i-chart" />
          </span>
          <span>{solution.result}</span>
        </div>
        <ol className="steps">
          {solution.steps.map((step, i) => (
            <li key={i}>
              <span className="sn">{i + 1}</span>
              <p>{step}</p>
            </li>
          ))}
        </ol>
        <div className="note">
          <Icon id="i-info" />
          <span>You left the session, so nothing from it counts as evidence of what you understand.</span>
        </div>
      </div>
    </div>
  );
}

export function EndedCard({ widget, onNewProblem }: { widget: Extract<Widget, { kind: "ended" }>; onNewProblem: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => lookAt(ref.current, "start"), []);
  // The backend has closed this session (a second NOT YET), so there is nothing more to send to it.
  return (
    <div className="icard" ref={ref}>
      <div className="paper stack">
        <span className="kicker">Session over · not yet</span>
        <p style={{ margin: 0 }}>{widget.message}</p>
        <div className="row">
          <button className="btn btn-main" type="button" onClick={onNewProblem}>
            Start a new problem <Icon id="i-arrow" className="arr" />
          </button>
        </div>
      </div>
    </div>
  );
}
