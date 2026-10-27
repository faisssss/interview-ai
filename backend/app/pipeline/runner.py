"""Run the processing steps for one meeting, saving each step's result before the next.

A retry starts at the first step missing from meeting.step_timings, so finished work (like a
long transcription) is never repeated. Steps that write rows delete the meeting's old rows
first, so re-running one never duplicates anything.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import cast
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import (
    ActionItem,
    Decision,
    Meeting,
    MeetingStatus,
    PipelineStep,
    Speaker,
    Summary,
    Utterance,
)
from app.pipeline.align import assign_speakers, group_utterances, label_speakers
from app.pipeline.errors import PermanentPipelineError
from app.pipeline.extract import (
    EXTRACTION_PROMPT_VERSION,
    NO_SPEECH_SUMMARY,
    ExtractionRequest,
    TranscriptLine,
    parse_due_date,
    resolve_owner,
    validate_evidence,
)
from app.pipeline.ingest import (
    DurationLimitError,
    decode_to_wav,
    duration_limit_message,
    encode_playback,
)
from app.pipeline.types import DiarizationResult, TranscriptResult
from app.providers.base import LanguageMode, Providers
from app.storage import LocalStorage, meeting_key

STEPS: tuple[PipelineStep, ...] = (
    PipelineStep.ingest,
    PipelineStep.transcribe,
    PipelineStep.diarize,
    PipelineStep.align,
    PipelineStep.extract,
)
EXTRACTION_WARNING = (
    "The summary, action items and decisions could not be generated. "
    "The transcript is complete. Use Retry to try again."
)
_SHORT_TEXT = 200  # owner_text and due_text column size


@dataclass(frozen=True)
class PipelineContext:
    session_factory: async_sessionmaker[AsyncSession]
    storage: LocalStorage
    providers: Providers
    settings: Settings


def _meeting_date(meeting: Meeting, timezone: str) -> date:
    return meeting.recorded_at.astimezone(ZoneInfo(timezone)).date()


async def _ingest(ctx: PipelineContext, session: AsyncSession, meeting: Meeting) -> None:
    wav = ctx.storage.path(meeting_key(meeting.id, "audio.wav"))
    duration_s = await asyncio.to_thread(decode_to_wav, ctx.storage.path(meeting.original_key), wav)
    limit = ctx.settings.max_duration_minutes
    if duration_s > limit * 60:
        raise DurationLimitError(duration_limit_message(limit))
    playback = ctx.storage.path(meeting_key(meeting.id, "playback.m4a"))
    await asyncio.to_thread(encode_playback, wav, playback)
    meeting.duration_s = duration_s


async def _transcribe(ctx: PipelineContext, session: AsyncSession, meeting: Meeting) -> None:
    wav = ctx.storage.path(meeting_key(meeting.id, "audio.wav"))
    language_mode = cast(LanguageMode, meeting.language_mode)
    result = await asyncio.to_thread(ctx.providers.transcriber.transcribe, wav, language_mode)
    artifact = ctx.storage.path(meeting_key(meeting.id, "transcript.json"))
    await asyncio.to_thread(artifact.write_text, result.model_dump_json(), "utf-8")


async def _diarize(ctx: PipelineContext, session: AsyncSession, meeting: Meeting) -> None:
    wav = ctx.storage.path(meeting_key(meeting.id, "audio.wav"))
    result = await asyncio.to_thread(ctx.providers.diarizer.diarize, wav)
    artifact = ctx.storage.path(meeting_key(meeting.id, "diarization.json"))
    await asyncio.to_thread(artifact.write_text, result.model_dump_json(), "utf-8")


async def _align(ctx: PipelineContext, session: AsyncSession, meeting: Meeting) -> None:
    transcript_file = ctx.storage.path(meeting_key(meeting.id, "transcript.json"))
    diarization_file = ctx.storage.path(meeting_key(meeting.id, "diarization.json"))
    transcript = TranscriptResult.model_validate_json(
        await asyncio.to_thread(transcript_file.read_text, "utf-8")
    )
    diarization = DiarizationResult.model_validate_json(
        await asyncio.to_thread(diarization_file.read_text, "utf-8")
    )
    raw_speakers = assign_speakers(transcript.words, diarization.turns)
    utterances = group_utterances(transcript.words, raw_speakers)

    await session.execute(delete(Utterance).where(Utterance.meeting_id == meeting.id))
    await session.execute(delete(Speaker).where(Speaker.meeting_id == meeting.id))
    speakers: dict[str, Speaker] = {}
    for raw_label, label in label_speakers(utterances).items():
        speakers[raw_label] = Speaker(
            meeting_id=meeting.id,
            label=label,
            voice_embedding=diarization.embeddings.get(raw_label),
        )
        session.add(speakers[raw_label])
    await session.flush()
    for seq, utterance in enumerate(utterances):
        session.add(
            Utterance(
                meeting_id=meeting.id,
                seq=seq,
                speaker_id=speakers[utterance.speaker].id,
                start_ms=utterance.start_ms,
                end_ms=utterance.end_ms,
                text=utterance.text,
                words=[word.model_dump() for word in utterance.words],
            )
        )


async def _extract(ctx: PipelineContext, session: AsyncSession, meeting: Meeting) -> None:
    for model in (ActionItem, Decision, Summary):
        await session.execute(delete(model).where(model.meeting_id == meeting.id))
    utterances = (
        await session.scalars(
            select(Utterance).where(Utterance.meeting_id == meeting.id).order_by(Utterance.seq)
        )
    ).all()
    if not utterances:
        session.add(
            Summary(
                meeting_id=meeting.id,
                overview=NO_SPEECH_SUMMARY,
                topics=[],
                model="none",
                prompt_version=EXTRACTION_PROMPT_VERSION,
            )
        )
        return

    speakers = (
        await session.scalars(select(Speaker).where(Speaker.meeting_id == meeting.id))
    ).all()
    label_by_speaker_id = {speaker.id: speaker.label for speaker in speakers}
    request = ExtractionRequest(
        meeting_date=_meeting_date(meeting, ctx.settings.timezone),
        lines=[
            TranscriptLine(
                seq=u.seq,
                speaker_label=label_by_speaker_id[u.speaker_id],
                start_ms=u.start_ms,
                text=u.text,
            )
            for u in utterances
        ],
    )
    output = await asyncio.to_thread(ctx.providers.extractor.extract, request)
    extraction = validate_evidence(output.extraction, {u.seq for u in utterances})
    utterance_id_by_seq = {u.seq: u.id for u in utterances}
    speaker_id_by_label = {speaker.label: speaker.id for speaker in speakers}

    session.add(
        Summary(
            meeting_id=meeting.id,
            overview=extraction.summary,
            topics=extraction.topics,
            model=output.model,
            prompt_version=output.prompt_version,
        )
    )
    for item in extraction.action_items:
        owner_speaker_id, owner_text = resolve_owner(item.owner, speaker_id_by_label)
        session.add(
            ActionItem(
                workspace_id=meeting.workspace_id,
                meeting_id=meeting.id,
                description=item.description,
                owner_speaker_id=owner_speaker_id,
                owner_text=owner_text[:_SHORT_TEXT] if owner_text else None,
                due_date=parse_due_date(item.due_date),
                due_text=item.due_text[:_SHORT_TEXT] if item.due_text else None,
                evidence_utterance_ids=[utterance_id_by_seq[seq] for seq in item.evidence],
                model=output.model,
                prompt_version=output.prompt_version,
            )
        )
    for decision in extraction.decisions:
        session.add(
            Decision(
                workspace_id=meeting.workspace_id,
                meeting_id=meeting.id,
                text=decision.text,
                evidence_utterance_ids=[utterance_id_by_seq[seq] for seq in decision.evidence],
                model=output.model,
                prompt_version=output.prompt_version,
            )
        )


_STEP_RUNNERS: dict[
    PipelineStep, Callable[[PipelineContext, AsyncSession, Meeting], Awaitable[None]]
] = {
    PipelineStep.ingest: _ingest,
    PipelineStep.transcribe: _transcribe,
    PipelineStep.diarize: _diarize,
    PipelineStep.align: _align,
    PipelineStep.extract: _extract,
}


async def process_meeting(ctx: PipelineContext, meeting_id: int) -> None:
    """Run every step not yet in step_timings. Raises on failure; the worker decides what next.

    A failing step's database writes are rolled back, and current_step still names it.
    """
    async with ctx.session_factory() as session:
        meeting = await session.get(Meeting, meeting_id)
        if meeting is None:
            raise PermanentPipelineError("This meeting no longer exists.")
        meeting.status = MeetingStatus.processing
        await session.commit()
        for step in STEPS:
            if step in meeting.step_timings:
                continue
            meeting.current_step = step
            await session.commit()
            started = time.perf_counter()
            await _STEP_RUNNERS[step](ctx, session, meeting)
            elapsed = round(time.perf_counter() - started, 1)
            meeting.step_timings = {**meeting.step_timings, step: elapsed}
            await session.commit()
        meeting.status = MeetingStatus.ready
        meeting.current_step = None
        await session.commit()


async def mark_meeting_failed(
    session: AsyncSession, meeting_id: int, step: str | None, message: str
) -> None:
    """Record a final failure. Notes failing after a finished transcript only add a warning."""
    meeting = await session.get(Meeting, meeting_id, populate_existing=True)
    if meeting is None:
        return
    if step == PipelineStep.extract and PipelineStep.align in meeting.step_timings:
        meeting.status = MeetingStatus.ready
        meeting.current_step = None
        meeting.warning = EXTRACTION_WARNING
    else:
        meeting.status = MeetingStatus.failed
        meeting.error = f"Failed at {step}: {message}" if step else message
