"""Rename a speaker, which links it to a person in the workspace."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import SessionDep, WorkspaceDep
from app.api.schemas import SpeakerOut, SpeakerRenameIn
from app.db.models import Meeting, Person, Speaker

router = APIRouter(prefix="/api")


@router.patch("/speakers/{speaker_id}")
async def rename_speaker(
    speaker_id: int, body: SpeakerRenameIn, session: SessionDep, workspace_id: WorkspaceDep
) -> SpeakerOut:
    """Link the speaker to the person with this name (ignoring case), creating them if new.

    The same name in another meeting links to the same person, which is how people are
    recognised across meetings.
    """
    speaker = await session.scalar(
        select(Speaker)
        .join(Meeting, Speaker.meeting_id == Meeting.id)
        .where(Speaker.id == speaker_id, Meeting.workspace_id == workspace_id)
    )
    if speaker is None:
        raise HTTPException(status_code=404, detail="Speaker not found.")
    person = await session.scalar(
        select(Person).where(
            Person.workspace_id == workspace_id, func.lower(Person.name) == func.lower(body.name)
        )
    )
    if person is None:
        person = Person(workspace_id=workspace_id, name=body.name)
        session.add(person)
        await session.flush()
    speaker.person_id = person.id
    await session.commit()
    return SpeakerOut(id=speaker.id, label=speaker.label, name=person.name)
