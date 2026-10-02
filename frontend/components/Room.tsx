"use client";

import { memo, useEffect, useRef } from "react";
import { room } from "@/lib/room";

/* The dark library behind everything. The drawing code is in lib/room.ts. */
export const Room = memo(function Room() {
  const stage = useRef<HTMLDivElement>(null);
  const scene = useRef<HTMLCanvasElement>(null);
  const motes = useRef<HTMLCanvasElement>(null);
  const sparks = useRef<HTMLCanvasElement>(null);
  const cursor = useRef<HTMLDivElement>(null);
  const veil = useRef<HTMLDivElement>(null);
  const flash = useRef<HTMLDivElement>(null);

  useEffect(
    () =>
      room.start({
        stage: stage.current!,
        scene: scene.current!,
        motes: motes.current!,
        sparks: sparks.current!,
        cursor: cursor.current!,
        veil: veil.current!,
        flash: flash.current!,
      }),
    [],
  );

  return (
    <>
      <div className="stage" ref={stage} aria-hidden="true">
        <canvas id="cvScene" ref={scene} />
        <div className="veil" ref={veil} />
        <div className="glow" />
        <div className="beam" />
        <div className="cursor-light" ref={cursor} />
        <div className="deep" />
        <canvas id="cvMotes" ref={motes} />
        <div className="flash" ref={flash} />
        <div className="vig" />
        <div className="grain" />
      </div>
      <canvas id="cvSparks" ref={sparks} aria-hidden="true" />
    </>
  );
});
