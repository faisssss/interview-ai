# interview-ai: Meeting Memory Assistant (Design Spec)

- **Status:** Draft, awaiting review
- **Date:** 2026-10-26
- **Scope:** The whole product. Each delivery phase (section 16) gets its own implementation plan before any code is written. If a phase changes a decision recorded here, this document is updated in the same change.

## 1. Summary

A web app that turns meetings into searchable team memory. You upload a recording or capture a meeting live. The app produces a transcript with speaker labels, a summary, action items and decisions. Across meetings it tracks people, what each person committed to, which tasks are still open and what was decided. It answers questions about all of it, with links to the exact moment in the recording.

Four things set it apart from a basic "transcribe and summarise" demo:

1. **Live mode.** Captions appear while people talk, and action items show up as they are spoken.
2. **Hindi–English (Hinglish) support.** Code-switched speech is transcribed, and summaries come out in English.
3. **Memory across meetings.** People, commitments and decisions are linked over time and queried by an agent that cites its sources.
4. **Measured quality.** Every core component has a benchmark, and the numbers are published in the README.

## 2. Goals and non-goals

**Goals**

- A visitor can open the hosted demo without signing up and see all four features above within two minutes.
- Locally, a 30-minute recording is fully processed in 5 minutes or less on the development laptop (RTX 3050, 4 GB VRAM).
- Every statement the app makes about a meeting can be traced to a timestamp in the recording.
- The repo shows production habits: tests, CI, typed code, database migrations and reproducible evaluations.

**Non-goals (v1)**

- Bots that join Zoom, Google Meet or Teams calls.
- User accounts, teams, sharing and permissions. Locally there is one workspace; the hosted demo gives each visitor a temporary sandbox.
- Integrations (calendar, Slack, Jira, email).
- Speaker labels during live mode. Speakers are identified after the meeting ends.
- Mobile apps, video or screen analysis, and summaries in languages other than English.

## 3. What the user sees

| Page | What it does |
|---|---|
| Home | Short pitch, **Start live meeting**, **Upload a recording**, **Try the demo**. |
| Meeting | Transcript with speaker labels; clicking a line plays the audio from that moment. Rename speakers and accept suggested names. Summary, action items (can be ticked off), decisions, and "updates from this meeting" to earlier tasks. While processing: a progress bar with the current step. |
| Live | Choose an audio source (microphone, or a Chrome tab plus microphone). Consent reminder. Captions stream in (grey while provisional, black once final). Action-item cards appear during the meeting. **End** finalises the meeting. |
| People | Everyone the app knows about. A person's page lists the meetings they were in, their commitments (open, done, overdue) and decisions they took part in. |
| Tasks | Every open action item across all meetings, grouped by owner, filterable by person and overdue. |
| Ask | Ask a question in plain language. The answer streams in, and each claim links to the moment in a recording where it was said. |

## 4. Architecture

```
Browser (Next.js)
  ├─ REST + SSE ───────────────► API (FastAPI)  ──┐
  └─ WebSocket (live audio) ───►   live sessions  │
                                                  ▼
                                   Postgres + pgvector
                                   (data, vectors, full-text, job queue)
                                                  ▲
                                   Worker ────────┘
                                     ├─ speech-to-text   [local GPU | Groq API]
                                     ├─ diarization      [pyannote]
                                     ├─ LLM              [Claude API]
                                     └─ text embeddings  [BGE-M3]

Audio files: local disk (development) or S3-compatible storage (hosted)
```

### Components

| Component | Technology | Responsibility |
|---|---|---|
| `frontend` | Next.js (App Router), TypeScript, Tailwind | All pages. API types are generated from FastAPI's OpenAPI schema (`openapi-typescript`) so the frontend and backend cannot drift apart. |
| `api` | FastAPI, Python 3.12, SQLAlchemy 2 (async), Pydantic v2 | REST endpoints, server-sent events for streamed answers, WebSocket for live mode. |
| `worker` | Same Python package, separate process | Runs pipeline jobs from the queue. |
| Database | Postgres 16 with pgvector, run with Docker Compose | All state: meetings, transcripts, people, tasks, vectors, full-text indexes and the job queue. |
| Storage | Local folder or S3-compatible bucket, behind one interface | Original uploads, processing audio and compressed playback copies. |

Python dependencies are managed with `uv` and pinned to Python 3.12 for this project. The machine's own Python 3.14 is not used.

### Providers: one switch between local and hosted

Every model sits behind a small interface with a local and a hosted implementation, chosen by environment variables (for example `ASR_PROVIDER=local|groq`).

| Capability | Local (development) | Hosted demo |
|---|---|---|
| Speech-to-text, uploads | faster-whisper `large-v3-turbo`, int8, GPU | Groq Whisper API |
| Speech-to-text, live | faster-whisper `small` (configurable), GPU | Groq Whisper API, one request per speech segment |
| Diarization (who spoke when) and voice embeddings | pyannote.audio, GPU | Decided in phase 5 (section 19) |
| LLM | Claude API | Claude API |
| Text embeddings | BGE-M3, GPU | BGE-M3, CPU |

**LLM settings.** Each LLM use has its own model and effort setting. All three default to Claude Opus 5.5 (`claude-opus-5-5`). Changing a model is a configuration change, and the evaluation suite (section 9) shows whether quality holds.

| Use | Default model | Effort |
|---|---|---|
| Extraction after a meeting | `claude-opus-5-5` | `medium` |
| Live action items | `claude-opus-5-5` | `low` |
| Ask (agent) | `claude-opus-5-5` | `medium` |

Structured results use the SDK's structured outputs (`client.messages.parse()` with Pydantic models). Calls with long inputs or outputs use streaming. Refusals are detected through `stop_reason`, and server-side fallbacks are enabled.

### Job queue in Postgres

Jobs live in a `jobs` table. Workers claim one with `SELECT … FOR UPDATE SKIP LOCKED`, and `LISTEN/NOTIFY` wakes idle workers immediately. A worker sends a heartbeat while it runs. Jobs whose heartbeat is older than 10 minutes are reclaimed. Failed steps retry up to 3 times with exponential backoff. This avoids running a separate queue service, and the common Python queues (Celery, RQ) do not officially support Windows anyway.

### GPU budget (4 GB VRAM)

The worker runs one GPU step at a time, loads each model when needed and frees it afterwards. Live mode runs its own small Whisper model in the API process, so a live session never waits for a background job. Approximate memory use, to be confirmed in phase 1: `large-v3-turbo` int8 1.5–2 GB, pyannote about 1 GB, BGE-M3 fp16 about 1.2 GB, `small` int8 about 0.5 GB.

## 5. Processing pipeline (uploads)

Each step saves its output before the next one starts, so a retry resumes at the step that failed. Each step's duration is stored and shown on the meeting page (for example "Processed in 2m 14s: transcribe 58s, diarize 41s…").

1. **Ingest.** Check the file type, duration (up to 3 hours locally, 15 minutes in the hosted demo) and size. Decode it to 16 kHz mono audio for processing and make a compressed copy for playback. Decoding uses PyAV, which bundles FFmpeg and is already a faster-whisper dependency, so FFmpeg does not need a separate install.
2. **Transcribe.** Word-level timestamps, with voice-activity filtering on. The language mode is `auto`, `en` or `hinglish` (section 8).
3. **Diarize.** Speaker turns, plus one voice embedding per speaker.
4. **Align.** Assign each word to the speaker turn it overlaps most (or the nearest turn if none). Group consecutive words from the same speaker into utterances, splitting at pauses longer than 1 second and at sentence ends. This is a pure function with unit tests.
5. **Extract.** One structured-output call to Claude over the whole transcript. A 3-hour meeting is about 40k tokens, well inside the context window, so no chunking is needed. The call returns:
   - a summary and topic list;
   - action items: description, owner, due date as spoken plus the resolved date, and evidence (utterance IDs);
   - decisions, with evidence;
   - suggested names for speakers, with evidence;
   - updates to open action items and decisions from earlier meetings (section 6).

   Any item whose evidence IDs do not exist in the transcript is dropped, which guards against invented content. The model ID and prompt version are stored with every result.
6. **Index.** Split the transcript into chunks of about 200–300 tokens that follow utterance boundaries (one utterance of overlap). Store a dense embedding and a Postgres full-text vector for each chunk.
7. **Link memory.** Resolve speakers and task owners to people, apply updates to earlier tasks and decisions, and compute voice-match suggestions.

While a meeting is processing, the meeting page polls its status every 2 seconds.

## 6. Memory across meetings

A **workspace** is the boundary of memory. Locally there is one workspace. The hosted demo has a read-only demo workspace plus one temporary sandbox per visitor.

### Entities

- **Person:** name, aliases, and an optional voice profile (the average of that person's confirmed voice embeddings).
- **Speaker:** one per voice per meeting, optionally linked to a person.
- **Action item:** description, owner (a person, or raw text such as "the design team"), due date, status (`open`, `done` or `dropped`), evidence.
- **Action item event:** a status change with its source (`llm` or `user`), meeting and evidence. Every event can be undone.
- **Decision:** text, evidence, and an optional link to an earlier decision it replaces.

### Linking speakers to people

Links are suggested and then confirmed. The app never merges people silently.

1. **Rename.** Renaming a speaker creates or links a person. This always wins.
2. **Name cues.** Extraction suggests names from context. For example, "Rahul, can you send…" is said just before Speaker B speaks, so Speaker B is probably Rahul. The suggestion is shown with its evidence and accepted with one click.
3. **Voice match.** The speaker's voice embedding is compared with each person's voice profile (cosine similarity). Above a threshold (set provisionally in phase 2, tuned in phase 4), the app suggests "Sounds like Priya (0.81)". Accepting it updates the profile. Voice profiles exist only for people the user has confirmed, and they are deleted with the person.

**Task owners** given as a speaker label map to that speaker's person. Owners given as a name are fuzzy-matched against people and aliases (rapidfuzz, high threshold). Anything else is kept as raw text and shown as unassigned.

### Tracking commitments over time

When meeting N is processed, the extraction call also receives the workspace's open action items (the 50 most recent, with ID, owner, description and date) and recent decisions. It returns status updates with evidence. For example, "I sent the deck yesterday" marks item 12 as done. It also reports decisions that replace earlier ones. Updates are applied automatically as action item events and listed on the meeting page under **Updates from this meeting**, each with an Undo button. An item is overdue when it is open and its due date has passed.

### Ask: an agent over memory

Claude answers questions using read-only tools scoped to the workspace:

| Tool | Returns |
|---|---|
| `search_transcripts(query, person?, date_from?, date_to?)` | Matching chunks: chunk ID, meeting, time range, text |
| `list_action_items(person?, status?, date_from?, date_to?)` | Action items with owners, status and evidence |
| `list_decisions(query?, date_from?, date_to?)` | Decisions, including which ones were replaced |
| `get_person(name)` | Person, aliases, meetings attended, commitment counts |

The loop is capped at 8 tool calls. The answer streams to the browser over server-sent events. Each claim cites chunk or utterance IDs, which the UI turns into play-from-timestamp links. A citation is removed if it points to an ID that no tool returned in that conversation.

**Search** is hybrid: dense vector search (pgvector, cosine) and full-text search (`ts_rank`), combined with reciprocal rank fusion (k = 60).

**Prompt injection.** Transcripts are untrusted input, since anyone in a meeting can say "ignore your instructions". The tools only read data and are limited to the current workspace, the agent has no network access, and its output is rendered as text, never as HTML.

## 7. Live mode

**Browser.** Audio comes from the microphone (`getUserMedia`), or from a Chrome tab (`getDisplayMedia`, for example a Google Meet tab) mixed with the microphone. An AudioWorklet converts it to 16 kHz mono 16-bit PCM and sends 100 ms frames over a WebSocket. A reminder to tell participants they are being recorded is shown before starting.

**Server, local GPU.** Silero VAD skips silence. A rolling buffer of up to 15 seconds is re-transcribed about once per second. Words that two consecutive passes agree on become final (the "local agreement" policy from whisper_streaming). The rest are sent as provisional text. Finalised audio is trimmed from the buffer at sentence boundaries.

**Server, hosted.** VAD splits speech at pauses, and each segment is sent to the Groq API. Captions arrive only as final text, with no provisional updates.

**Live action items.** After about every 45 seconds of new final text, one LLM call reads the last 3 minutes of transcript and the items already found, and returns only new items. They are pushed to the browser as cards marked provisional.

**Ending a meeting.** The server saves the audio as it streams. On **End**, the normal upload pipeline runs on the full recording. The final transcript, speakers and extraction replace the live view. Target: under 2 minutes for a 30-minute meeting on the local GPU.

**Resilience.** If the connection drops, the browser reconnects with the session ID and resends frames the server has not acknowledged. The server keeps the session for 60 seconds after a disconnect.

**Latency targets** (local GPU): provisional caption 1.5 s or less after speech (median), final caption 3 s or less (median). Phase 3 builds the latency measurement; phase 4 publishes it with the other results.

## 8. Hindi–English support

- **Speech-to-text.** Whisper handles Hindi and English, but code-switched speech is inconsistent: it may switch scripts or translate instead of transcribing. Phase 4 compares three configurations on a code-switched test set: automatic language detection; a Hindi language hint with a romanised Hinglish prompt; and an English hint with the same prompt. The best one becomes the `hinglish` mode.
- **Text.** Devanagari text is also stored transliterated to Roman script, for search and for a display toggle. The original is always kept.
- **Outputs.** Summaries, action items and decisions are always written in English. Evidence quotes stay exactly as spoken.
- **Search.** BGE-M3 is multilingual, so English questions can find Hinglish passages. Full-text search runs over the romanised text.

## 9. Evaluation

The `eval/` folder holds the evaluation harness. Each suite runs with one command and writes JSON plus a Markdown table to `eval/results/`, recording the git commit, models and settings used. The README publishes the latest table.

| Suite | Data | Metrics |
|---|---|---|
| Speech-to-text, English | AMI Meeting Corpus test meetings, headset mix and single distant microphone | Word error rate (WER) |
| Speech-to-text, Hinglish | A public code-switched set if its licence allows (for example the MUCS 2021 Hindi–English data); otherwise a 30-minute recording made with consent and transcribed by hand | WER and character error rate (CER), after normalising spelling and script |
| Diarization | AMI test meetings | Diarization error rate (DER), using `pyannote.metrics` |
| Extraction | AMI meetings, whose human-written summaries list actions and decisions | Precision, recall and F1 for action items and decisions. Matching uses an LLM judge that is spot-checked against manual labels. |
| Retrieval and Ask | About 50 hand-written questions over AMI scenario series (the same team across 4 meetings) | Recall@k for dense, full-text and hybrid search; answer correctness (LLM judge); citation precision |
| Memory | A small, hand-labelled set of meetings in sequence | Precision and recall of task-status updates and speaker-name suggestions |
| Live latency | Recordings replayed through the WebSocket at real speed | Provisional and final caption latency (median and 95th percentile), local vs hosted |

Bulk LLM calls in evaluations use the Message Batches API, which costs half as much. The LLM-judge prompts and their agreement with manual labels are published with the results. The AMI corpus is licensed CC BY 4.0 and is credited in the README.

## 10. Data model (Postgres)

| Table | Key columns |
|---|---|
| `workspaces` | id, kind (`local`, `demo`, `sandbox`), expires_at |
| `meetings` | id, workspace_id, title, recorded_at (editable; used to resolve "by Friday"), duration, source (`upload`, `live`), status, current_step, step_timings, error, audio paths, language_mode |
| `speakers` | id, meeting_id, label, person_id, voice_embedding |
| `people` | id, workspace_id, name, aliases, voice_profile |
| `utterances` | id, meeting_id, speaker_id, start_ms, end_ms, text, text_roman, words (JSON with per-word timings) |
| `chunks` | id, meeting_id, first and last utterance_id, start_ms, end_ms, text, embedding (vector), search_text (tsvector) |
| `summaries` | meeting_id, overview, topics, model, prompt_version |
| `action_items` | id, workspace_id, meeting_id, description, owner_person_id, owner_text, due_date, due_text, status, evidence_utterance_ids, provisional, model, prompt_version |
| `action_item_events` | id, action_item_id, meeting_id, kind (`completed`, `reopened`, `dropped`, `updated`), source (`llm`, `user`), evidence_utterance_ids, undone |
| `decisions` | id, workspace_id, meeting_id, text, evidence_utterance_ids, supersedes_id, model, prompt_version |
| `speaker_suggestions` | id, speaker_id, person_id or suggested name, reason (`name_cue`, `voice`), score, evidence, status |
| `jobs` | id, kind, payload, status, attempts, run_after, locked_by, heartbeat_at, current_step, last_error |

Schema changes go through Alembic migrations.

## 11. API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/meetings` | Upload a recording and queue processing |
| GET | `/api/meetings`, `/api/meetings/{id}` | List meetings; one meeting with transcript, summary, items and decisions |
| GET | `/api/meetings/{id}/audio` | Playback audio, with HTTP range support for seeking |
| PATCH | `/api/speakers/{id}` | Rename a speaker or link it to a person |
| POST | `/api/suggestions/{id}/accept` | Accept a speaker-name suggestion |
| GET | `/api/people`, `/api/people/{id}` | People and their commitments |
| GET, PATCH | `/api/action-items`, `/api/action-items/{id}` | List with filters; change status |
| POST | `/api/action-item-events/{id}/undo` | Undo an automatic update |
| POST | `/api/ask` | Ask a question; the answer streams back as server-sent events |
| WS | `/ws/live` | Live session: audio in; captions and action items out |
| GET | `/api/health` | Health check |

FastAPI serves interactive API documentation at `/docs`.

## 12. Error handling

- **Uploads.** Unsupported or corrupt files and recordings over the duration limit are rejected with a clear message.
- **Jobs.** Per-step checkpoints, up to 3 attempts with backoff. After that the meeting shows "failed at <step>" with a **Retry** button.
- **Partial success.** If extraction fails but the transcript succeeded, the meeting is still usable and shows a warning.
- **GPU out of memory.** The step is retried on the CPU or with the next smaller model, and the fallback is logged.
- **LLM.** The SDK retries rate-limit and server errors. Responses are validated against their schema, evidence IDs that do not exist are dropped, and `stop_reason` is checked for `refusal` and `max_tokens`.
- **Live mode.** The browser reconnects automatically. Audio is saved as it arrives, so closing the browser loses nothing already sent.
- **Hosted limits.** When a provider limit or the daily budget is reached, users see a "demo is busy, try again later" message instead of an error page.

## 13. Security and privacy

- **What leaves the machine.** In local mode, audio stays on the machine. Transcript text is sent to the Claude API. In hosted mode, audio is also sent to the Groq API.
- **Hosted demo limits.** Sandbox data (audio, transcripts, voice profiles) is deleted after 24 hours. Uploads are capped at 15 minutes, live sessions at 5 minutes, and Ask questions at 10 per visitor per day. A global daily spending cap applies.
- **Secrets.** API keys come from environment variables. `.env` is git-ignored, and keys are never logged.
- **Voice profiles** are biometric-like data. They are stored only for confirmed people, can be deleted, and are never used outside their workspace.
- **Prompt injection.** See section 6.
- **Origins.** The API and WebSocket accept requests only from the app's own origin.
- **Consent.** Live mode reminds the user to tell participants they are being recorded.

## 14. Testing and CI

- **Unit tests (pytest):** word-to-speaker alignment, utterance grouping, chunking, rank fusion, owner and name resolution, the local-agreement streaming logic, evidence validation, and job claiming and retries.
- **Fake providers:** deterministic speech-to-text, diarization, LLM and embedding stand-ins, so the full pipeline runs in tests without a GPU or network access.
- **Integration tests:** API and worker against a real Postgres (Docker Compose locally, a service container in CI).
- **LLM parsing:** tested against recorded example responses.
- **Frontend:** type checking, linting, a production build, and one Playwright smoke test (upload a fixture, see the transcript) that uses the fake providers.
- **CI (GitHub Actions)** on every push and pull request: ruff (lint and format), pyright, pytest, and the frontend checks. Tests that need a GPU or paid APIs are marked and run only locally.

## 15. Repository layout

```
backend/              FastAPI app, worker, pipeline, providers, live mode (uv project)
frontend/             Next.js app
eval/                 Evaluation harness, dataset download scripts, results
docs/                 Specs, plans, architecture notes, screenshots
docker-compose.yml    Postgres with pgvector
.github/workflows/    CI
```

## 16. Delivery phases

Each phase ends in a working, demonstrable state and gets its own implementation plan first.

| Phase | Delivers | Done when |
|---|---|---|
| 1. Core pipeline | Tooling, CI, Postgres, job queue, the upload pipeline (transcript with speakers, summary, action items, decisions), the meeting page with click-to-play and speaker renaming | A 30-minute recording is processed end to end locally in 5 minutes or less |
| 2. Memory and Ask | People, speaker suggestions (name cues and voice), task tracking across meetings, decisions, hybrid search, the Ask agent, the People, Tasks and Ask pages | Over a 4-meeting AMI series, "what is still open for X?" gets a correct, cited answer |
| 3. Live mode | WebSocket streaming, provisional and final captions, microphone and tab audio, live action items, finalising on End | A 10-minute live session meets the latency targets and produces a full result after End |
| 4. Hinglish and evaluation | Hinglish mode, transliteration, all evaluation suites, the results table | The README shows reproducible numbers for every suite |
| 5. Polish and deploy | Hosted providers, the demo workspace (AMI series plus Hinglish meetings recorded with consent), landing page, limits and budget guard, README with a demo GIF and architecture diagram | A public URL works without signing up |

## 17. Cost estimates

| Item | Estimate |
|---|---|
| Processing one uploaded 30-minute meeting (Claude Opus 5.5: about 9k tokens in, 2k out plus thinking) | $0.10–0.20 |
| Live mode, 30 minutes (about 40 action-item calls at `low` effort) | $1–2 |
| One Ask question (a few tool calls) | $0.10–0.20 |
| API spend for development and evaluation, phases 1–4 | About $20–40 |
| Groq Whisper (hosted speech-to-text) | A few cents per audio hour; confirm current pricing in phase 5 |
| Hosting | Frontend on a free tier; backend and database on a small server (about $5–10 per month) or free tiers; chosen in phase 5 |

Claude Opus 5.5 is priced at $4 per million input tokens and $20 per million output tokens. All figures above are estimates. Actual token usage is logged per call.

## 18. Prerequisites (one-time setup)

- Docker Desktop, to run Postgres.
- An Anthropic API key.
- A Hugging Face account, with the pyannote model terms accepted, to download the diarization model.
- An NVIDIA driver recent enough for CUDA 12. CUDA libraries come from pip packages; this is verified in phase 1.
- A Groq API key (phase 5 only).

## 19. Decisions deferred to a later phase

These do not block phase 1.

- **Hosted diarization (phase 5):** pyannote on CPU for short clips, or a hosted API. This also decides whether voice matching works for visitor uploads; it always works on the pre-loaded demo meetings.
- **Hinglish test data (phase 4):** depends on dataset licensing.
- **Hosted embedding model (phase 4):** BGE-M3 on CPU, or a smaller multilingual model if the retrieval evaluation shows little loss.
- **Product name:** the repository is `interview-ai`; the app's display name can differ.

## 20. Glossary

- **Diarization:** working out who spoke when.
- **WER / CER:** word and character error rate, the share of words or characters a transcript gets wrong (lower is better).
- **DER:** diarization error rate, the share of time assigned to the wrong speaker or missed (lower is better).
- **VAD:** voice activity detection, which separates speech from silence.
- **Embedding:** a list of numbers representing meaning (for text) or voice characteristics (for speakers), used for similarity search.
- **Reciprocal rank fusion:** a simple way to merge two ranked result lists into one.
- **Recall@k:** how often the right passage appears in the top k search results.
