"use client";

import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "@/lib/fx";
import { room } from "@/lib/room";
import { useApp } from "./AppProvider";
import { Icon } from "./Icons";

/* The wax seal that stamps onto the screen when the fresh problem is solved. */
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
    <div className={`seal-wrap${open ? " show" : ""}`} role="dialog" aria-modal="true" aria-label="Transfer verified" aria-hidden={!open}>
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
          <path d="M150 8c18 0 22 10 38 14s28-2 38 10 2 24 10 38 20 18 18 36-14 18-14 36 12 26 2 40-24 6-36 16-12 26-30 30-26-8-42-8-24 12-40 4-10-26-24-36-28-4-36-20 6-24 0-40-18-22-10-38 22-12 30-26 2-30 16-40 26 2 42-2S132 8 150 8z" fill="url(#wax)" />
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
          <div className="big">Transfer verified</div>
          <p>You used the idea on your own, in a new setting.</p>
          <button className="btn btn-accent" type="button" ref={go} onClick={onContinue}>
            See what changed <Icon id="i-arrow" className="arr" />
          </button>
        </div>
      </div>
    </div>
  );
}
