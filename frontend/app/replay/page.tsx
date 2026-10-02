import Link from "next/link";
import { SavedReplays } from "@/components/SavedReplays";
import { RECORDINGS } from "@/lib/tutor/replay";

/** /replay: the recorded sessions that can be replayed. */
export default function ReplayIndex() {
  return (
    <main className="wrap" style={{ paddingTop: 48 }}>
      <section className="view">
        <p className="eyebrow">Recorded sessions</p>
        <h1>Replay a Master session</h1>
        <p className="lede">Each one plays a real recorded session through the real screens, with no backend or model. Press Enter to send each pre-filled answer.</p>
        <div className="stack">
          {Object.values(RECORDINGS).map((r) => (
            <Link key={r.id} href={`/replay/${r.id}`} className="paper" style={{ display: "block" }}>
              <span className="kicker">{r.title}</span>
              <p style={{ margin: "6px 0 0" }}>{r.problem}</p>
              {r.note && <p className="muted" style={{ margin: "8px 0 0", fontSize: 14 }}>{r.note}</p>}
            </Link>
          ))}
        </div>
        <SavedReplays />
      </section>
    </main>
  );
}
