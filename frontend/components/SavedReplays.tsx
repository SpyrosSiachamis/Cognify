"use client";

import Link from "next/link";
import { useState, useSyncExternalStore, type ChangeEvent } from "react";
import { downloadRecording, listSaved, readRecordingFile, removeSaved, saveRecording, subscribeSaved } from "@/lib/tutor/recorder";
import type { Recording } from "@/lib/tutor/replay";

/** Replays saved in this browser (from a session's result screen, or imported from a downloaded file). */
export function SavedReplays() {
  // null on the server: the storage exists only in the browser.
  const saved = useSyncExternalStore<Recording[] | null>(subscribeSaved, listSaved, () => null);
  const [message, setMessage] = useState("");

  const importFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const recording = await readRecordingFile(file);
      setMessage(saveRecording(recording) ? `Imported “${recording.title}”.` : "This browser would not store the replay.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="stack" style={{ marginTop: 28 }}>
      <span className="kicker">Saved in this browser</span>
      {saved && saved.length === 0 && <p className="muted" style={{ margin: 0 }}>None yet. Finish a session and press “Save as replay” on the result screen.</p>}
      {saved?.map((r) => (
        <div key={r.id} className="paper">
          <Link href={`/replay/saved?id=${encodeURIComponent(r.id)}`} style={{ display: "block" }}>
            <span className="kicker">{r.title}</span>
            <p style={{ margin: "6px 0 0" }}>{r.label}</p>
          </Link>
          <div className="row" style={{ marginTop: 10 }}>
            <button type="button" className="link" onClick={() => downloadRecording(r)}>Download the file</button>
            <button
              type="button"
              className="link"
              onClick={() => removeSaved(r.id)}
            >
              Remove
            </button>
          </div>
        </div>
      ))}
      <label className="muted" style={{ fontSize: 14 }}>
        Import a replay file: <input type="file" accept="application/json,.json" onChange={importFile} />
      </label>
      {message && <p className="muted" role="status" style={{ margin: 0 }}>{message}</p>}
    </div>
  );
}
