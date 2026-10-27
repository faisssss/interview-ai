# interview-ai

[![CI](https://github.com/faisssss/interview-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/faisssss/interview-ai/actions/workflows/ci.yml)

A meeting memory assistant. Upload a recording and get a transcript that shows who said what, a summary, action items and decisions. Every action item and decision links back to the moment in the recording where it was said.

## Features

| Feature | Status |
|---|---|
| **Upload a recording.** Transcript with speaker labels, a summary with topics, action items with owners and due dates, and decisions. Click any line to play the audio from there. Rename speakers and tick off action items. | Working (phase 1) |
| **Memory across meetings.** People, their commitments and decisions tracked over time, and an Ask page that answers questions with links to the exact moments. | Planned (phase 2) |
| **Live mode.** Captions while people talk, and action items as they are spoken. | Planned (phase 3) |
| **Hindi–English (Hinglish).** Code-switched speech in, English notes out. | Planned (phase 4) |
| **Measured quality.** Published numbers for speech-to-text accuracy, speaker detection and extraction. | Processing speed in phase 1; full evaluation in phase 4 |

## How it works

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

This is the full design. Phase 1 builds the upload path: the REST API, the worker, Postgres, the local speech models and Claude.

When you upload a recording, the API saves the file and adds a job to a queue in Postgres. A separate worker process picks up the job and runs five steps, saving each step's result before starting the next:

1. **Ingest.** Check the file, convert it to 16 kHz mono audio and make a compressed copy for playback. Anything FFmpeg can read works, including video files.
2. **Transcribe.** faster-whisper `large-v3-turbo` on the GPU, with a timestamp for every word.
3. **Diarize.** pyannote.audio works out who spoke when.
4. **Align.** Each word goes to the speaker who was talking at that moment, and words are grouped into lines.
5. **Extract.** Claude reads the transcript and returns a summary, action items and decisions as structured data. Each item must cite the transcript lines it comes from, and items citing lines that don't exist are dropped.

While the job runs, the meeting page shows the current step. When it finishes, the page shows how long each step took.

### Engineering notes

- **Job queue in Postgres.** Workers claim jobs with `SELECT … FOR UPDATE SKIP LOCKED` and are woken by `LISTEN/NOTIFY`. Running jobs send heartbeats, so a job whose worker died is picked up again after 10 minutes. A failed job is tried up to 3 times in total, with exponential backoff between tries. There is no Redis or Celery to run.
- **Resumable pipeline.** A retry starts at the step that failed. If only the notes step fails, the transcript is still usable and the meeting shows a warning with a retry button.
- **Swappable models.** Each model sits behind a small interface (`Transcriber`, `Diarizer`, `Extractor`) chosen by environment variables. Deterministic fakes let the whole pipeline run in tests and CI without a GPU or network access.
- **Fits in 4 GB of VRAM.** The worker loads one model at a time and frees it afterwards. If the GPU runs out of memory, the step is retried on the CPU.
- **Typed from database to browser.** SQLAlchemy 2 models and Pydantic schemas on the backend; TypeScript types generated from FastAPI's OpenAPI schema on the frontend. CI fails if the generated types are out of date.
- **Checked LLM output.** Claude's response is parsed into Pydantic models with structured outputs. Refusals and cut-off responses are detected, and the model ID and prompt version are stored with every result.

**Tech stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, Postgres 16 with pgvector, PyAV, faster-whisper, pyannote.audio, PyTorch, the Claude API, Next.js 16, React 19, TypeScript, Tailwind CSS 4, Vitest, Playwright and GitHub Actions.

## Quick start

### Prerequisites

- [uv](https://docs.astral.sh/uv/), which also installs Python 3.12 for the project
- [Docker Desktop](https://www.docker.com/products/docker-desktop/), for Postgres
- [Node.js](https://nodejs.org/) 24

To use the real models you also need:

- an NVIDIA GPU with a recent driver (developed on an RTX 3050 laptop GPU with 4 GB of memory);
- a [Hugging Face](https://huggingface.co/) read token, after accepting the terms of [`pyannote/speaker-diarization-community-1`](https://huggingface.co/pyannote/speaker-diarization-community-1);
- an [Anthropic API key](https://console.anthropic.com/).

To try the app without these, see [Run without a GPU or API keys](#run-without-a-gpu-or-api-keys).

### Run it

Start Postgres from the repository root:

```bash
docker compose up -d --wait db
```

In `backend/`, copy `.env.example` to `.env` and fill in `HF_TOKEN` and `ANTHROPIC_API_KEY`. Then install, create the tables and start the API:

```bash
uv sync --extra ml
uv run python -m alembic upgrade head
uv run python -m uvicorn app.api.main:app --port 8000
```

In a second terminal, start the worker from `backend/`:

```bash
uv run python -m app.jobs.worker
```

In a third terminal, start the frontend from `frontend/`:

```bash
npm ci
npm run dev
```

Open http://localhost:3000 and upload a recording. The API documentation is at http://localhost:8000/docs.

### Run without a GPU or API keys

Set these in `backend/.env`, and run `uv sync` instead of `uv sync --extra ml`:

```
ASR_PROVIDER=fake
DIARIZATION_PROVIDER=fake
LLM_PROVIDER=fake
```

Every upload then gets the same two scripted transcript lines and a placeholder summary. The tests and CI run this way.

### Windows notes

Windows Smart App Control can block the small `.exe` launchers that Python tools install. Running each tool as a module (`uv run python -m pytest` instead of `uv run pytest`) avoids this, so every command in this README uses that form.

## Configuration

Settings come from environment variables or `backend/.env`. [`backend/.env.example`](backend/.env.example) lists every setting with its default.

| Variable | Default | What it does |
|---|---|---|
| `ASR_PROVIDER` | `local` | Speech-to-text: `local` (faster-whisper) or `fake` |
| `DIARIZATION_PROVIDER` | `local` | Speaker detection: `local` (pyannote) or `fake` |
| `LLM_PROVIDER` | `claude` | Notes: `claude` or `fake` |
| `ML_DEVICE` | `cuda` | `cuda` for an NVIDIA GPU, or `cpu` (slower, works anywhere) |
| `ASR_MODEL` | `large-v3-turbo` | faster-whisper model |
| `ASR_BATCH_SIZE` | `8` | Audio chunks transcribed at once; lower it if the GPU runs out of memory |
| `HF_TOKEN` | none | Hugging Face token for the pyannote model |
| `ANTHROPIC_API_KEY` | none | Claude API key |
| `LLM_MODEL_EXTRACT` | `claude-opus-5-5` | Claude model for summaries, action items and decisions |
| `LLM_EFFORT_EXTRACT` | `medium` | How much thinking Claude does for them |
| `TIMEZONE` | `Asia/Kolkata` | Used to turn "by Friday" into a date |
| `MAX_UPLOAD_MB` | `500` | Largest upload |
| `MAX_DURATION_MINUTES` | `180` | Longest recording |
| `DATABASE_URL` | the Docker Postgres | Database connection |
| `STORAGE_DIR` | `data` | Folder for uploads and processing files |

The frontend reads `NEXT_PUBLIC_API_URL`, which defaults to `http://localhost:8000`.

## Tests

Backend, from `backend/`. The tests need the Postgres container and create their own `meetings_test` database.

```bash
uv run python -m pytest
uv run python -m ruff check .
uv run python -m ruff format --check .
uv run python -m pyright
```

Two groups of tests are skipped by default, because they need a GPU or cost money:

```bash
uv run python -m pytest -m gpu
uv run python -m pytest -m paid
```

`gpu` runs faster-whisper and pyannote on the GPU (it needs `uv sync --extra ml` and `HF_TOKEN`). `paid` makes one real Claude call (it needs `ANTHROPIC_API_KEY`).

Frontend, from `frontend/`:

```bash
npm run lint
npm run typecheck
npm test
```

The end-to-end test uploads a recording in a real browser, waits for the notes and renames a speaker. Start the API and the worker with fake models, then run:

```bash
npm run build
npx playwright install chromium
npm run e2e
```

GitHub Actions runs all of these on every push and pull request, except the `gpu` and `paid` tests.

## Phase 1 benchmark

The goal: a 30-minute recording processed in 5 minutes or less on the development laptop (RTX 3050 laptop GPU, 4 GB).

The test recording is meeting ES2002b from the AMI Meeting Corpus (headset mix, about 73 MB). Download it from `backend/`:

```bash
uv run python -m scripts.fetch_ami_sample ES2002b
```

Then upload `backend/data/samples/ES2002b.wav` on the home page. When processing finishes, the meeting page shows the time each step took.

Results will be added here after the first run with the real models.

## Roadmap

| Phase | Delivers |
|---|---|
| **1. Core pipeline** (current) | The upload pipeline, the meeting page, the job queue and CI |
| **2. Memory and Ask** | People, speaker-name suggestions, task tracking across meetings, hybrid search, and an Ask agent that cites its sources |
| **3. Live mode** | Captions streamed over a WebSocket, and live action items |
| **4. Hinglish and evaluation** | Hinglish mode, transliteration, and published accuracy numbers for every component |
| **5. Polish and deploy** | A hosted demo with no sign-up, demo meetings, and usage limits |

The full design is in [docs/specs/2026-10-26-meeting-assistant-design.md](docs/specs/2026-10-26-meeting-assistant-design.md).

## Project layout

```
backend/               API, worker, pipeline and model providers (uv project)
  app/api/             REST endpoints
  app/jobs/            Postgres job queue and worker
  app/pipeline/        ingest, align, extract and the step runner
  app/providers/       faster-whisper, pyannote, Claude and test fakes
  migrations/          Alembic database migrations
  scripts/             GPU check and sample download
  tests/               pytest suites
frontend/              Next.js app (App Router, TypeScript, Tailwind)
docs/specs/            design spec
docker-compose.yml     Postgres 16 with pgvector
.github/workflows/     CI
```

## Privacy

Speech-to-text and speaker detection run on your machine, so the audio never leaves it. The transcript text is sent to the Claude API to write the notes. API keys are read from `backend/.env`, which git ignores.

## Credits

- Test recordings come from the [AMI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/corpus/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Speech-to-text uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with OpenAI's Whisper `large-v3-turbo` model. Speaker detection uses [pyannote.audio](https://github.com/pyannote/pyannote-audio).
