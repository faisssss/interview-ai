"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { type LanguageMode, uploadMeeting } from "@/lib/api";

/** "2026-10-27" → that day at 12:00 local time, so deadlines like "by Friday" resolve right. */
function noonOn(day: string): string {
  return new Date(`${day}T12:00:00`).toISOString();
}

export function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [meetingDate, setMeetingDate] = useState("");
  const [languageMode, setLanguageMode] = useState<LanguageMode>("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const meeting = await uploadMeeting(file, {
        title: title.trim() || undefined,
        languageMode,
        recordedAt: meetingDate ? noonOn(meetingDate) : undefined,
      });
      router.push(`/meetings/${meeting.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed.");
      setBusy(false);
    }
  }

  const field = "mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900";
  return (
    <form
      onSubmit={onSubmit}
      className="space-y-4 rounded-2xl border border-slate-200 p-6 shadow-sm dark:border-slate-800"
    >
      <label className="block text-sm font-medium">
        Recording
        <input
          type="file"
          accept="audio/*,video/*"
          required
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="mt-1 block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 dark:file:bg-slate-800"
        />
      </label>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="block text-sm font-medium sm:col-span-3">
          Title (optional)
          <input value={title} onChange={(e) => setTitle(e.target.value)} className={field} />
        </label>
        <label className="block text-sm font-medium sm:col-span-2">
          Meeting date
          <input
            type="date"
            value={meetingDate}
            onChange={(e) => setMeetingDate(e.target.value)}
            className={field}
          />
          <span className="mt-1 block text-xs font-normal text-slate-500">Leave empty for today</span>
        </label>
        <label className="block text-sm font-medium">
          Language
          <select
            value={languageMode}
            onChange={(e) => setLanguageMode(e.target.value as LanguageMode)}
            className={field}
          >
            <option value="auto">Detect automatically</option>
            <option value="en">English</option>
          </select>
        </label>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy || !file}
        className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 dark:bg-white dark:text-slate-900"
      >
        {busy ? "Uploading…" : "Upload"}
      </button>
    </form>
  );
}
