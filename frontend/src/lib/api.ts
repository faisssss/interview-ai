import createClient from "openapi-fetch";
import type { components, paths } from "./api-types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Typed client generated from the backend's OpenAPI schema (npm run gen:api). */
export const api = createClient<paths>({ baseUrl: API_URL });

type Schemas = components["schemas"];
export type MeetingSummary = Schemas["MeetingSummaryOut"];
export type MeetingDetail = Schemas["MeetingDetailOut"];
export type Utterance = Schemas["UtteranceOut"];
export type Speaker = Schemas["SpeakerOut"];
export type ActionItem = Schemas["ActionItemOut"];
export type Decision = Schemas["DecisionOut"];
export type LanguageMode = "auto" | "en";

/** The API's error detail: a message string, or the first of FastAPI's validation errors. */
export function errorMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("detail" in body)) return null;
  const { detail } = body as { detail: unknown };
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first: unknown = detail[0];
    if (typeof first === "object" && first !== null && "msg" in first) {
      const { msg } = first as { msg: unknown };
      if (typeof msg === "string") return msg;
    }
  }
  return null;
}

/** Upload a recording. Throws an Error with the API's message when it is rejected. */
export async function uploadMeeting(
  file: File,
  options: { title?: string; languageMode: LanguageMode; recordedAt?: string },
): Promise<MeetingSummary> {
  const form = new FormData();
  form.append("file", file);
  form.append("language_mode", options.languageMode);
  if (options.title) form.append("title", options.title);
  if (options.recordedAt) form.append("recorded_at", options.recordedAt);
  const response = await fetch(`${API_URL}/api/meetings`, { method: "POST", body: form });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body) ?? `Upload failed (HTTP ${response.status}).`);
  }
  return body as MeetingSummary;
}

export function audioUrl(meetingId: number): string {
  return `${API_URL}/api/meetings/${meetingId}/audio`;
}
