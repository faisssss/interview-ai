"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { MeetingNotes } from "@/components/MeetingNotes";
import { ProcessingStatus } from "@/components/ProcessingStatus";
import { TranscriptView } from "@/components/TranscriptView";
import { api, audioUrl, type MeetingDetail } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { findActiveUtterance, formatProcessingTime } from "@/lib/meeting";

const POLL_MS = 2000;

type LoadResult = { meeting: MeetingDetail } | { error: string };

async function fetchMeeting(meetingId: number): Promise<LoadResult> {
  try {
    const { data, response } = await api.GET("/api/meetings/{meeting_id}", {
      params: { path: { meeting_id: meetingId } },
    });
    if (data) return { meeting: data };
    return { error: response.status === 404 ? "Meeting not found." : "Could not load this meeting." };
  } catch {
    return { error: "Could not reach the server." };
  }
}

export function MeetingView() {
  const { id } = useParams<{ id: string }>();
  const meetingId = Number(id);
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [playheadMs, setPlayheadMs] = useState(0);
  const audioRef = useRef<HTMLAudioElement>(null);

  const apply = useCallback((result: LoadResult) => {
    if ("meeting" in result) {
      setMeeting(result.meeting);
      setLoadError(null);
    } else {
      setLoadError(result.error);
    }
  }, []);

  const reload = useCallback(() => fetchMeeting(meetingId).then(apply), [meetingId, apply]);

  useEffect(() => {
    void fetchMeeting(meetingId).then(apply);
  }, [meetingId, apply]);

  // While the worker is busy, poll so the progress bar and results appear on their own.
  const inProgress = meeting?.status === "queued" || meeting?.status === "processing";
  useEffect(() => {
    if (!inProgress) return;
    const timer = setInterval(() => void reload(), POLL_MS);
    return () => clearInterval(timer);
  }, [inProgress, reload]);

  function playFrom(ms: number) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = ms / 1000;
    void audio.play();
  }

  async function retry() {
    await api.POST("/api/meetings/{meeting_id}/retry", {
      params: { path: { meeting_id: meetingId } },
    });
    await reload();
  }

  if (!meeting) {
    return (
      <main className="mx-auto w-full max-w-5xl px-4 py-12 text-sm text-slate-500">
        {loadError ?? "Loading…"}
      </main>
    );
  }

  const ready = meeting.status === "ready";
  const recorded = new Date(meeting.recorded_at).toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">{meeting.title}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {recorded}
          {meeting.duration_s ? ` · ${formatDuration(meeting.duration_s)}` : ""}
        </p>
      </header>

      <ProcessingStatus meeting={meeting} onRetry={() => void retry()} />

      {meeting.utterances.length > 0 && (
        <>
          <audio
            ref={audioRef}
            controls
            preload="metadata"
            src={audioUrl(meeting.id)}
            onTimeUpdate={(event) => setPlayheadMs(event.currentTarget.currentTime * 1000)}
            className="sticky top-0 z-10 w-full"
          />
          <div className="grid gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <section aria-label="Transcript">
              <TranscriptView
                meeting={meeting}
                activeIndex={findActiveUtterance(meeting.utterances, playheadMs)}
                onPlay={playFrom}
                onRenamed={() => void reload()}
              />
            </section>
            <aside>
              <MeetingNotes meeting={meeting} onPlay={playFrom} onChanged={() => void reload()} />
            </aside>
          </div>
        </>
      )}

      {ready && meeting.utterances.length === 0 && meeting.summary && (
        <p className="text-sm">{meeting.summary.overview}</p>
      )}

      {ready && Object.keys(meeting.step_timings).length > 0 && (
        <footer className="text-xs text-slate-500">{formatProcessingTime(meeting.step_timings)}</footer>
      )}
    </main>
  );
}
