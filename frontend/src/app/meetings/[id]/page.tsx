import { Suspense } from "react";
import { MeetingView } from "@/components/MeetingView";

// The meeting ID is only known at request time, so the part that reads it (useParams)
// renders inside Suspense; the fallback is what gets prerendered.
export default function MeetingPage() {
  return (
    <Suspense
      fallback={<main className="mx-auto w-full max-w-5xl px-4 py-12 text-sm text-slate-500">Loading…</main>}
    >
      <MeetingView />
    </Suspense>
  );
}
