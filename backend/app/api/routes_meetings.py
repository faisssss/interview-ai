"""Upload, list and view meetings."""

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, SettingsDep, StorageDep, WorkspaceDep
from app.api.schemas import (
    ActionItemOut,
    DecisionOut,
    MeetingDetailOut,
    MeetingSummaryOut,
    SpeakerOut,
    SummaryOut,
    UtteranceOut,
)
from app.db.models import ActionItem, Decision, Meeting, Person, Speaker, Summary, Utterance
from app.jobs.queue import JOB_PROCESS_MEETING, enqueue
from app.pipeline import ingest
from app.storage import UploadTooLargeError, meeting_key

router = APIRouter(prefix="/api")

_SAFE_SUFFIX = re.compile(r"\.[a-z0-9]{1,10}")


def _original_name(filename: str | None) -> str:
    """original + the upload's extension, kept only if it is short and plain."""
    suffix = Path(filename or "").suffix.lower()
    return "original" + (suffix if _SAFE_SUFFIX.fullmatch(suffix) else "")


def _default_title(filename: str | None) -> str:
    return Path(filename or "").stem.strip() or "Untitled recording"


async def get_meeting(session: AsyncSession, meeting_id: int, workspace_id: int) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None or meeting.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return meeting


async def meeting_detail(session: AsyncSession, meeting: Meeting) -> MeetingDetailOut:
    speaker_rows = (
        await session.execute(
            select(Speaker, Person.name)
            .outerjoin(Person, Speaker.person_id == Person.id)
            .where(Speaker.meeting_id == meeting.id)
            .order_by(Speaker.id)
        )
    ).all()
    display_names = {speaker.id: name or speaker.label for speaker, name in speaker_rows}
    utterances = (
        await session.scalars(
            select(Utterance).where(Utterance.meeting_id == meeting.id).order_by(Utterance.seq)
        )
    ).all()
    summary = await session.get(Summary, meeting.id)
    action_items = (
        await session.scalars(
            select(ActionItem).where(ActionItem.meeting_id == meeting.id).order_by(ActionItem.id)
        )
    ).all()
    decisions = (
        await session.scalars(
            select(Decision).where(Decision.meeting_id == meeting.id).order_by(Decision.id)
        )
    ).all()
    return MeetingDetailOut(
        **MeetingSummaryOut.model_validate(meeting).model_dump(),
        step_timings=meeting.step_timings,
        error=meeting.error,
        warning=meeting.warning,
        language_mode=meeting.language_mode,
        speakers=[
            SpeakerOut(id=speaker.id, label=speaker.label, name=name)
            for speaker, name in speaker_rows
        ],
        utterances=[UtteranceOut.model_validate(u) for u in utterances],
        summary=SummaryOut(overview=summary.overview, topics=summary.topics) if summary else None,
        action_items=[
            ActionItemOut(
                id=item.id,
                description=item.description,
                owner=(
                    display_names.get(item.owner_speaker_id)
                    if item.owner_speaker_id is not None
                    else item.owner_text
                ),
                due_date=item.due_date,
                due_text=item.due_text,
                status=item.status,  # pyright: ignore[reportArgumentType]  (validated into the enum)
                evidence=item.evidence_utterance_ids,
            )
            for item in action_items
        ],
        decisions=[
            DecisionOut(id=d.id, text=d.text, evidence=d.evidence_utterance_ids) for d in decisions
        ],
    )


@router.post("/meetings", status_code=201)
async def upload_meeting(
    session: SessionDep,
    workspace_id: WorkspaceDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    language_mode: Annotated[Literal["auto", "en"], Form()] = "auto",
    recorded_at: Annotated[datetime | None, Form()] = None,
) -> MeetingSummaryOut:
    meeting = Meeting(
        workspace_id=workspace_id,
        title=(title or "").strip() or _default_title(file.filename),
        recorded_at=recorded_at or datetime.now(UTC),
        language_mode=language_mode,
        original_key="",
    )
    session.add(meeting)
    await session.flush()
    meeting.original_key = meeting_key(meeting.id, _original_name(file.filename))

    async def reject(status_code: int, detail: str) -> HTTPException:
        storage.delete_prefix(meeting_key(meeting.id, ""))
        await session.rollback()
        return HTTPException(status_code=status_code, detail=detail)

    try:
        await storage.save_upload(
            meeting.original_key, file, max_bytes=settings.max_upload_mb * 1024 * 1024
        )
        info = await asyncio.to_thread(ingest.probe_audio, storage.path(meeting.original_key))
    except UploadTooLargeError:
        raise await reject(413, f"Files can be up to {settings.max_upload_mb} MB.") from None
    except ingest.UnsupportedMediaError as exc:
        raise await reject(422, str(exc)) from None
    if info.duration_s is not None and info.duration_s > settings.max_duration_minutes * 60:
        raise await reject(422, ingest.duration_limit_message(settings.max_duration_minutes))

    await enqueue(
        session,
        JOB_PROCESS_MEETING,
        {"meeting_id": meeting.id},
        max_attempts=settings.job_max_attempts,
    )
    await session.commit()
    return MeetingSummaryOut.model_validate(meeting)


@router.get("/meetings")
async def list_meetings(session: SessionDep, workspace_id: WorkspaceDep) -> list[MeetingSummaryOut]:
    meetings = await session.scalars(
        select(Meeting)
        .where(Meeting.workspace_id == workspace_id)
        .order_by(Meeting.created_at.desc(), Meeting.id.desc())
    )
    return [MeetingSummaryOut.model_validate(meeting) for meeting in meetings]


@router.get("/meetings/{meeting_id}")
async def get_meeting_detail(
    meeting_id: int, session: SessionDep, workspace_id: WorkspaceDep
) -> MeetingDetailOut:
    return await meeting_detail(session, await get_meeting(session, meeting_id, workspace_id))
