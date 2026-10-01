"use client";

import { useEffect, useRef } from "react";
import { lookAt } from "@/lib/fx";
import type { Rich } from "@/lib/tutor/types";
import { Icon } from "../Icons";
import { RichText } from "../RichText";

/** A tutor bubble. While `paragraphs` is null it shows the three typing dots. */
export function TutorMsg({ paragraphs }: { paragraphs: Rich[] | null }) {
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
          <span className="typing">
            <i />
            <i />
            <i />
          </span>
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
