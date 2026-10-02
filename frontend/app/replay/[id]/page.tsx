import { notFound } from "next/navigation";
import { App } from "@/components/App";
import { RECORDINGS } from "@/lib/tutor/replay";

// Only the recorded sessions exist; anything else is a 404.
export const dynamicParams = false;
export const generateStaticParams = () => Object.keys(RECORDINGS).map((id) => ({ id }));

/** /replay/<id>: a recorded Master session played through the real screens, for presenting. */
export default async function ReplayPage({ params }: { params: Promise<{ id: string }> }) {
  const recording = RECORDINGS[(await params).id];
  if (!recording) notFound();
  return <App recording={recording} />;
}
