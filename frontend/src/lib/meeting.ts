export const STEP_LABELS: Record<string, string> = {
  ingest: "Preparing audio",
  transcribe: "Transcribing",
  diarize: "Identifying speakers",
  align: "Matching words to speakers",
  extract: "Writing summary and action items",
};

const STEP_PROGRESS: Record<string, number> = {
  ingest: 5,
  transcribe: 20,
  diarize: 50,
  align: 75,
  extract: 85,
};

/** Rough percentage for the progress bar: where the pipeline has got to. */
export function stepProgress(status: string, step: string | null): number {
  if (status === "ready") return 100;
  if (status !== "processing" || step === null) return 0;
  return STEP_PROGRESS[step] ?? 0;
}

/** Index of the last utterance that has started by `ms` (binary search), or -1. */
export function findActiveUtterance(utterances: { start_ms: number }[], ms: number): number {
  let low = 0;
  let high = utterances.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (utterances[middle].start_ms <= ms) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

/** "Processed in 2m 14s: ingest 3s, transcribe 58s, …" in the order the steps ran. */
export function formatProcessingTime(timings: Record<string, number>): string {
  const total = Math.round(Object.values(timings).reduce((sum, seconds) => sum + seconds, 0));
  const minutes = Math.floor(total / 60);
  const elapsed = minutes > 0 ? `${minutes}m ${total % 60}s` : `${total}s`;
  const steps = Object.entries(timings)
    .map(([step, seconds]) => `${step} ${Math.round(seconds)}s`)
    .join(", ");
  return `Processed in ${elapsed}: ${steps}`;
}
