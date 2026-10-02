"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { App } from "@/components/App";
import { findSaved, subscribeSaved } from "@/lib/tutor/recorder";
import type { Recording } from "@/lib/tutor/replay";

function savedFromUrl(): Recording | null {
  const id = new URLSearchParams(window.location.search).get("id");
  return id ? findSaved(id) : null;
}

/** /replay/saved?id=…: a replay saved in this browser, played through the real screens. */
export default function SavedReplayPage() {
  // undefined on the server (the storage exists only in the browser); null when this browser has no such replay.
  const recording = useSyncExternalStore<Recording | null | undefined>(subscribeSaved, savedFromUrl, () => undefined);
  if (recording === undefined) return null;
  if (!recording)
    return (
      <main className="wrap" style={{ paddingTop: 48 }}>
        <section className="view">
          <p className="lede">That replay is not saved in this browser. Import its file on the replay list.</p>
          <Link className="link" href="/replay">Back to the replays</Link>
        </section>
      </main>
    );
  return <App recording={recording} />;
}
