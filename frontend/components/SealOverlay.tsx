"use client";

import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "@/lib/fx";
import { room } from "@/lib/room";
import { useApp } from "./AppProvider";
import { Icon } from "./Icons";

/** The scalloped wax outline, centred on the seal's rings at (150, 150): radius 132 with 12 bumps of 10.
    Computed once from geometry, so it is always centred and renders the same on the server and the client. */
function waxOutline(cx = 150, cy = 150, radius = 132, bumps = 12, depth = 10, samples = 240): string {
  const points = Array.from({ length: samples }, (_, i) => {
    const a = (2 * Math.PI * i) / samples;
    const r = radius + depth * Math.cos(bumps * a);
    return `${(cx + r * Math.sin(a)).toFixed(1)} ${(cy - r * Math.cos(a)).toFixed(1)}`;
  });
  return `M${points.join("L")}Z`;
}
const WAX = waxOutline();

/* The wax seal that stamps onto the screen when the backend returns a VERIFIED verdict. */
export function SealOverlay({ onContinue }: { onContinue: () => void }) {
  const { state } = useApp();
  const go = useRef<HTMLButtonElement>(null);
  const open = state.sealOpen;

  // A flash of light and a burst of sparks once the seal has landed, then focus the button.
  useEffect(() => {
    if (!open) return;
    const reduced = prefersReducedMotion();
    const fx = setTimeout(() => {
      room.flash();
      room.burst(innerWidth / 2, innerHeight * 0.4);
    }, reduced ? 0 : 800);
    const focus = setTimeout(() => go.current?.focus(), 1300);
    return () => {
      clearTimeout(fx);
      clearTimeout(focus);
    };
  }, [open]);

  return (
    <div className={`seal-wrap${open ? " show" : ""}`} role="dialog" aria-modal="true" aria-label="Verified" aria-hidden={!open} inert={!open}>
      <div className="rays" />
      <div className="seal-inner">
        <svg className="seal" viewBox="0 0 300 300" aria-hidden="true">
          <defs>
            <radialGradient id="wax" cx="40%" cy="32%" r="75%">
              <stop offset="0" style={{ stopColor: "var(--seal-a)" }} />
              <stop offset=".5" style={{ stopColor: "var(--seal-b)" }} />
              <stop offset="1" style={{ stopColor: "var(--seal-c)" }} />
            </radialGradient>
            <path id="ringPath" d="M150,150 m-104,0 a104,104 0 1,1 208,0 a104,104 0 1,1 -208,0" />
          </defs>
          <path d={WAX} fill="url(#wax)" />
          <circle cx="150" cy="150" r="118" fill="none" style={{ stroke: "var(--accent-2)" }} strokeOpacity=".6" strokeWidth="1.5" />
          <circle cx="150" cy="150" r="88" fill="none" style={{ stroke: "var(--accent-2)" }} strokeOpacity=".6" strokeWidth="1.5" />
          <g className="seal-ring">
            <text fontFamily="Hanken Grotesk, sans-serif" fontSize="15.5" fontWeight="700" letterSpacing="5.2" style={{ fill: "var(--accent-2)" }}>
              <textPath href="#ringPath">TRANSFER VERIFIED · COGNIFY · TRANSFER VERIFIED · COGNIFY ·</textPath>
            </text>
          </g>
          <g fill="none" style={{ stroke: "var(--accent-2)" }} strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round" transform="translate(150 152) scale(2.3) translate(-28 -28)">
            <path d="M7 35c9-3.400 16-2.600 21 2.400 5-5 12-5.800 21-2.400v9.500c-9-3.200-16-2.400-21 2.800-5-5.200-12-6-21-2.800z" strokeWidth="2" />
            <path d="M28 34C22 28 22 20 28 9c6 11 6 19 0 25z" strokeWidth="2" />
            <path d="M25.500 34c-7-2.500-11-8.500-11-16 7 1.800 10.500 7.500 11 16zM30.500 34c7-2.500 11-8.500 11-16-7 1.800-10.500 7.500-11 16z" strokeWidth="2" />
          </g>
        </svg>
        <div className="seal-copy">
          <div className="big">Verified</div>
          <p>{state.session.verdict?.evidence ?? "You solved the fresh problem on your own."}</p>
          <button className="btn btn-accent" type="button" ref={go} onClick={onContinue}>
            See what changed <Icon id="i-arrow" className="arr" />
          </button>
        </div>
      </div>
    </div>
  );
}
