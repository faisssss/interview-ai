import { expect, test } from "vitest";
import { findActiveUtterance, formatProcessingTime, stepProgress } from "./meeting";

test("stepProgress follows the pipeline", () => {
  expect(stepProgress("queued", null)).toBe(0);
  expect(
    ["ingest", "transcribe", "diarize", "align", "extract"].map((s) => stepProgress("processing", s)),
  ).toEqual([5, 20, 50, 75, 85]);
  expect(stepProgress("ready", null)).toBe(100);
});

test("findActiveUtterance returns the last utterance that has started", () => {
  const utterances = [{ start_ms: 200 }, { start_ms: 1500 }, { start_ms: 4000 }];
  expect(findActiveUtterance(utterances, 100)).toBe(-1);
  expect(findActiveUtterance(utterances, 1200)).toBe(0);
  expect(findActiveUtterance(utterances, 1500)).toBe(1);
  expect(findActiveUtterance(utterances, 99_999)).toBe(2);
  expect(findActiveUtterance([], 0)).toBe(-1);
});

test("formatProcessingTime totals and lists the steps", () => {
  expect(
    formatProcessingTime({ ingest: 3.2, transcribe: 58.4, diarize: 41, align: 0.3, extract: 31.1 }),
  ).toBe("Processed in 2m 14s: ingest 3s, transcribe 58s, diarize 41s, align 0s, extract 31s");
  expect(formatProcessingTime({ ingest: 0.2, transcribe: 0.1 })).toBe(
    "Processed in 0s: ingest 0s, transcribe 0s",
  );
});
