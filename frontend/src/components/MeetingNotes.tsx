"use client";

import { type ActionItem, api, type MeetingDetail } from "@/lib/api";

function dueLabel(item: ActionItem): string | null {
  if (item.due_date) {
    const day = new Date(`${item.due_date}T00:00:00`).toLocaleDateString(undefined, {
      weekday: "short",
      day: "numeric",
      month: "short",
    });
    return `due ${day}`;
  }
  return item.due_text ?? null;
}

export function MeetingNotes({
  meeting,
  onPlay,
  onChanged,
}: {
  meeting: MeetingDetail;
  onPlay: (ms: number) => void;
  onChanged: () => void;
}) {
  const startById = new Map(meeting.utterances.map((u) => [u.id, u.start_ms]));

  function jumpButton(evidence: number[]) {
    const start = evidence.map((id) => startById.get(id)).find((ms) => ms !== undefined);
    if (start === undefined) return null;
    return (
      <button
        type="button"
        onClick={() => onPlay(start)}
        className="text-xs font-medium text-slate-500 underline hover:text-slate-900 dark:hover:text-white"
      >
        Jump to quote
      </button>
    );
  }

  async function toggle(item: ActionItem) {
    const { error } = await api.PATCH("/api/action-items/{item_id}", {
      params: { path: { item_id: item.id } },
      body: { status: item.status === "done" ? "open" : "done" },
    });
    if (!error) onChanged();
  }

  const { summary } = meeting;
  return (
    <div className="space-y-8">
      {summary && (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Summary</h2>
          <p className="mt-2 text-sm leading-6">{summary.overview}</p>
          {summary.topics.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-2">
              {summary.topics.map((topic) => (
                <li key={topic} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs dark:bg-slate-800">
                  {topic}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Action items</h2>
        {meeting.action_items.length === 0 && <p className="mt-2 text-sm text-slate-500">None.</p>}
        <ul className="mt-2 space-y-3">
          {meeting.action_items.map((item) => (
            <li key={item.id} className="flex gap-3">
              <input
                type="checkbox"
                checked={item.status === "done"}
                onChange={() => void toggle(item)}
                aria-label={`Mark "${item.description}" as done`}
                className="mt-1"
              />
              <div className="text-sm">
                <p className={item.status === "done" ? "text-slate-400 line-through" : ""}>
                  {item.description}
                </p>
                <p className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-slate-500">
                  {item.owner && <span>{item.owner}</span>}
                  {dueLabel(item) && <span>{dueLabel(item)}</span>}
                  {jumpButton(item.evidence)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Decisions</h2>
        {meeting.decisions.length === 0 && <p className="mt-2 text-sm text-slate-500">None.</p>}
        <ul className="mt-2 space-y-3">
          {meeting.decisions.map((decision) => (
            <li key={decision.id} className="text-sm">
              <p>{decision.text}</p>
              <p className="mt-0.5">{jumpButton(decision.evidence)}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
