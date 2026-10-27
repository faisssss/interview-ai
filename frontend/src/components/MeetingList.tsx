"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type MeetingSummary } from "@/lib/api";
import { formatDuration } from "@/lib/format";

const STATUS_STYLES: Record<MeetingSummary["status"], string> = {
  queued: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  processing: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  ready: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
};

export function MeetingList() {
  const [meetings, setMeetings] = useState<MeetingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.GET("/api/meetings").then(({ data, error: failure }) => {
      if (data) setMeetings(data);
      else setError(failure ? "Could not load meetings." : null);
    }, () => setError("Could not reach the server."));
  }, []);

  return (
    <section>
      <h2 className="text-lg font-semibold">Recent meetings</h2>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      {meetings === null && !error && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
      {meetings?.length === 0 && <p className="mt-2 text-sm text-slate-500">No meetings yet.</p>}
      <ul className="mt-3 divide-y divide-slate-200 dark:divide-slate-800">
        {meetings?.map((meeting) => (
          <li key={meeting.id}>
            <Link
              href={`/meetings/${meeting.id}`}
              className="flex items-center justify-between gap-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-900"
            >
              <span>
                <span className="font-medium">{meeting.title}</span>
                <span className="block text-xs text-slate-500">
                  {new Date(meeting.recorded_at).toLocaleDateString(undefined, {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                  {meeting.duration_s ? ` · ${formatDuration(meeting.duration_s)}` : ""}
                </span>
              </span>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[meeting.status]}`}>
                {meeting.status}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
