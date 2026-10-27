"use client";

import { useEffect, useRef } from "react";
import { RENAME_HINT_ID, SpeakerName } from "@/components/SpeakerName";
import type { MeetingDetail } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";

export function TranscriptView({
  meeting,
  activeIndex,
  onPlay,
  onRenamed,
}: {
  meeting: MeetingDetail;
  activeIndex: number;
  onPlay: (ms: number) => void;
  onRenamed: () => void;
}) {
  const speakers = new Map(meeting.speakers.map((speaker) => [speaker.id, speaker]));
  const activeRow = useRef<HTMLLIElement>(null);

  useEffect(() => {
    activeRow.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeIndex]);

  if (meeting.utterances.length === 0) {
    return <p className="text-sm text-slate-500">No speech was detected.</p>;
  }
  return (
    <>
      <span id={RENAME_HINT_ID} className="sr-only">
        Rename this speaker
      </span>
      <ol className="space-y-1">
        {meeting.utterances.map((utterance, index) => {
          const speaker = speakers.get(utterance.speaker_id);
          const active = index === activeIndex;
          return (
            <li
              key={utterance.id}
              ref={active ? activeRow : undefined}
              id={`utterance-${utterance.id}`}
              className={`flex items-start gap-3 rounded-lg px-2 py-1.5 ${active ? "bg-amber-100 dark:bg-amber-900/30" : ""}`}
            >
              {speaker && <SpeakerName speaker={speaker} onRenamed={onRenamed} />}
              <button
                type="button"
                aria-label={`Play from ${formatTimestamp(utterance.start_ms)}: ${utterance.text}`}
                onClick={() => onPlay(utterance.start_ms)}
                className="flex flex-1 gap-3 text-left text-sm"
              >
                <span className="shrink-0 font-mono text-xs leading-5 text-slate-500">
                  {formatTimestamp(utterance.start_ms)}
                </span>
                <span>{utterance.text}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </>
  );
}
