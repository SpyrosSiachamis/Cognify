"use client";

import type { Verdict } from "@/lib/api";
import { gapLabel } from "@/lib/vocab";
import { Icon } from "../Icons";

/* "Why it is not verified yet": explains a NOT YET verdict in plain words, using only what the backend
   returned. The backend counts a fresh problem as VERIFIED only when the answer is correct AND it is the
   student's own work (no more help than allowed), so a NOT YET means one of those was missing. */
export function NotVerifiedCard({ verdict, hintsUsed, over }: { verdict: Verdict; hintsUsed: number; over: boolean }) {
  const { independent, remaining_gap: gap, evidence, changes } = verdict;
  const concept = changes.concept;

  const rows: { name: string; pill: string; label: string; why: string }[] = [
    independent
      ? { name: "Your own work", pill: "strong", label: "yes", why: "You solved the fresh problem without extra help, so it could count." }
      : {
          name: "Your own work",
          pill: "weak",
          label: "not yet",
          why: `You needed ${hintsUsed} ${hintsUsed === 1 ? "hint" : "hints"} in this session, or the check found the answer was not fully your own. A fresh problem only counts as proven when you solve it on your own.`,
        },
    independent
      ? { name: "Correct answer", pill: "weak", label: "not yet", why: "Your answer to the fresh problem was not correct yet. That is the part to work on." }
      : { name: "Correct answer", pill: "untested", label: "not counted", why: "Because the help needed was too high, correctness alone could not make it verified." },
  ];
  if (gap) rows.push({ name: "Still open", pill: "fragile", label: gapLabel(gap), why: "This is the step Cognify will keep working on with you." });

  return (
    <div className="paper stack">
      <div className="side-title">
        <h3>Why it is not verified yet</h3>
        <span className="pill weak">not yet</span>
      </div>
      <blockquote className="evidence">
        {evidence}
        <cite>Cognify&rsquo;s check of your fresh problem</cite>
      </blockquote>
      <ul className="signals">
        {rows.map((r) => (
          <li key={r.name}>
            <span className="nm">{r.name}</span>
            <span className={`pill ${r.pill}`}>{r.label}</span>
            <span className="why">{r.why}</span>
          </li>
        ))}
        <li>
          <span className="nm">{concept.name}</span>
          <span className={`pill ${concept.after}`}>{concept.after}</span>
          <span className="why">{concept.before === concept.after ? `Stays ${concept.after} until a fresh problem is solved on your own.` : `Moved from ${concept.before} to ${concept.after}.`}</span>
        </li>
      </ul>
      <div className="note">
        <Icon id="i-info" />
        <span>
          {over
            ? "This session has ended. Start a new problem when you are ready; what you showed today is kept as evidence."
            : "Not yet is new evidence, not a failure. Cognify goes back to teaching this step, then gives you another fresh problem."}
        </span>
      </div>
    </div>
  );
}
