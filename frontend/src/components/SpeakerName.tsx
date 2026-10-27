"use client";

import { useState } from "react";
import { api, type Speaker } from "@/lib/api";

/** ID of the visually hidden "Rename this speaker" hint that TranscriptView renders once. */
export const RENAME_HINT_ID = "rename-speaker-hint";

/** The speaker's name as a button; click to rename (Enter saves, Escape cancels). */
export function SpeakerName({ speaker, onRenamed }: { speaker: Speaker; onRenamed: () => void }) {
  const display = speaker.name ?? speaker.label;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(display);
  const [saving, setSaving] = useState(false);

  async function save() {
    const name = draft.trim();
    if (!name || name === display) {
      setEditing(false);
      return;
    }
    setSaving(true);
    const { error } = await api.PATCH("/api/speakers/{speaker_id}", {
      params: { path: { speaker_id: speaker.id } },
      body: { name },
    });
    setSaving(false);
    if (!error) {
      setEditing(false);
      onRenamed();
    }
  }

  if (editing) {
    return (
      <input
        aria-label="Speaker name"
        autoFocus
        value={draft}
        disabled={saving}
        maxLength={80}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => setEditing(false)}
        onKeyDown={(event) => {
          if (event.key === "Enter") void save();
          if (event.key === "Escape") setEditing(false);
        }}
        className="w-36 rounded border border-slate-300 px-1.5 py-0.5 text-xs dark:border-slate-700 dark:bg-slate-900"
      />
    );
  }
  return (
    <button
      type="button"
      aria-describedby={RENAME_HINT_ID}
      onClick={() => {
        setDraft(display);
        setEditing(true);
      }}
      className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
    >
      {display}
    </button>
  );
}
