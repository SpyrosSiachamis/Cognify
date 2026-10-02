"use client";

import { memo, useEffect, useRef, useState, type ReactNode } from "react";
import type { TabId } from "@/lib/state";
import { useActions, useAppSelector } from "./AppProvider";
import { Icon } from "./Icons";
import { OverviewTab } from "./drawer/OverviewTab";
import { ReasoningTab } from "./drawer/ReasoningTab";
import { TeachingTab } from "./drawer/TeachingTab";
import { UnderstandingTab } from "./drawer/UnderstandingTab";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "reasoning", label: "Your reasoning" },
  { id: "understanding", label: "Understanding" },
  { id: "teaching", label: "Teaching" },
];

const CONTENT: Record<TabId, () => ReactNode> = {
  overview: () => <OverviewTab />,
  reasoning: () => <ReasoningTab />,
  understanding: () => <UnderstandingTab />,
  teaching: () => <TeachingTab />,
};

/* The right-hand sheet where all the analysis lives. ESC closes it and Tab stays inside it. */
export const ProgressDrawer = memo(function ProgressDrawer({ onRefresh }: { onRefresh: () => void }) {
  const { dispatch } = useActions();
  const open = useAppSelector((s) => s.sheetOpen);
  const tab = useAppSelector((s) => s.tab);
  const sheetRev = useAppSelector((s) => s.sheetRev);
  const views = useAppSelector((s) => s.views);
  // The tab content (charts, the constellation) is only built while the drawer can be seen:
  // while it is open, and for the slide-out after closing.
  const [mounted, setMounted] = useState(open);
  if (open && !mounted) setMounted(true);
  useEffect(() => {
    if (open || !mounted) return;
    const t = setTimeout(() => setMounted(false), 600);
    return () => clearTimeout(t);
  }, [open, mounted]);
  const sheet = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);

  const closeSheet = () => dispatch({ type: "sheet", open: false });

  // On open: remember what had focus, scroll to the top and focus the close button. On close: give focus back.
  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    body.current?.scrollTo({ top: 0 });
    const t = setTimeout(() => close.current?.focus(), 350);
    return () => {
      clearTimeout(t);
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return closeSheet();
      if (e.key !== "Tab" || !sheet.current) return;
      const items = Array.from(sheet.current.querySelectorAll<HTMLElement>('button,[tabindex="0"],a[href]')).filter((x) => x.offsetParent !== null || x instanceof SVGElement);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <>
      <div className={`scrim${open ? " show" : ""}`} onClick={closeSheet} />
      <div className={`sheet${open ? " show" : ""}`} ref={sheet} role="dialog" aria-modal="true" aria-label="Your progress" aria-hidden={!open} data-source={views.status}>
        <div className="sheet-head">
          <div>
            <h2>
              Your <em>progress</em>
            </h2>
            <p>Everything Cognify has learned about how you think.</p>
          </div>
          <button className="xbtn" type="button" ref={close} aria-label="Close progress" onClick={closeSheet}>
            <Icon id="i-close" />
          </button>
        </div>
        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => { dispatch({ type: "tab", tab: t.id }); body.current?.scrollTo({ top: 0 }); }}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="sheet-body" ref={body} key={`${tab}-${sheetRev}`}>
          {mounted && CONTENT[tab]()}
        </div>
        <div className="sheet-foot">
          <span>{views.status === "ok" && views.data.learner.is_seeded ? "Includes seeded demo history (labelled “seeded”). This session is live." : "Everything here comes from the Cognify backend."}</span>
          <button className="btn-ghost" type="button" onClick={onRefresh}>
            <Icon id="i-undo" style={{ verticalAlign: -2, marginRight: 6 }} />
            Refresh
          </button>
        </div>
      </div>
    </>
  );
});
