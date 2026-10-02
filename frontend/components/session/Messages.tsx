"use client";

import { useEffect, useRef, useState } from "react";
import { lookAt } from "@/lib/fx";
import { nextProgressAt, progressLine } from "@/lib/messages";
import type { Rich } from "@/lib/tutor/types";
import { Icon } from "../Icons";
import { RichText } from "../RichText";

/** The typing dots; for a turn, after a few seconds, a short line says what Cognify is doing. */
function Waiting({ progress }: { progress: boolean }) {
  const [line, setLine] = useState<string | null>(null);
  useEffect(() => {
    if (!progress) return;
    const start = Date.now();
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      const due = nextProgressAt(Date.now() - start);
      if (due === null) return;
      timer = setTimeout(() => {
        setLine(progressLine(Date.now() - start));
        schedule();
      }, due - (Date.now() - start));
    };
    schedule();
    return () => clearTimeout(timer);
  }, [progress]);
  return (
    <>
      <span className="typing">
        <i />
        <i />
        <i />
      </span>
      {line && <span className="waiting-line">{line}</span>}
    </>
  );
}

/** A tutor bubble. While `paragraphs` is null it shows the typing dots (with progress lines when `progress`). */
export function TutorMsg({ paragraphs, progress = false }: { paragraphs: Rich[] | null; progress?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => lookAt(ref.current, "end"), [paragraphs]);
  return (
    <div className="msg tutor" ref={ref}>
      <span className="av">
        <Icon id="i-wave" />
      </span>
      <div className="bub">
        {paragraphs ? (
          paragraphs.map((p, i) => (
            // pre-line keeps the backend's line breaks (lists, small tables) instead of running them together
            <p key={i} style={{ whiteSpace: "pre-line" }}>
              <RichText value={p} />
            </p>
          ))
        ) : (
          <Waiting progress={progress} />
        )}
      </div>
    </div>
  );
}

export function YouMsg({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => lookAt(ref.current, "end"), []);
  return (
    <div className="msg you" ref={ref}>
      <div className="bub">{text}</div>
    </div>
  );
}
