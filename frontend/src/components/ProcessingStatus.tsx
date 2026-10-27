import type { MeetingDetail } from "@/lib/api";
import { STEP_LABELS, stepProgress } from "@/lib/meeting";

const retryButton =
  "rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white dark:bg-white dark:text-slate-900";

export function ProcessingStatus({
  meeting,
  onRetry,
}: {
  meeting: MeetingDetail;
  onRetry: () => void;
}) {
  if (meeting.status === "queued") {
    return <p className="text-sm text-slate-500">Waiting for the worker to pick this up…</p>;
  }
  if (meeting.status === "processing") {
    const label = meeting.current_step ? STEP_LABELS[meeting.current_step] : "Starting";
    return (
      <div className="space-y-2">
        <p className="text-sm">{label}…</p>
        <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className="h-full rounded-full bg-slate-900 transition-all dark:bg-white"
            style={{ width: `${stepProgress(meeting.status, meeting.current_step)}%` }}
          />
        </div>
      </div>
    );
  }
  const problem = meeting.status === "failed" ? meeting.error : meeting.warning;
  if (!problem) return null;
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950/40"
    >
      <p>{problem}</p>
      <button type="button" onClick={onRetry} className={retryButton}>
        Retry
      </button>
    </div>
  );
}
