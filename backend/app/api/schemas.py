"""Request and response bodies. The frontend's TypeScript types are generated from these."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.db.models import ActionItemStatus, MeetingStatus, PipelineStep


class MeetingSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    recorded_at: datetime
    duration_s: float | None
    status: MeetingStatus
    current_step: PipelineStep | None
    created_at: datetime


class SpeakerOut(BaseModel):
    id: int
    label: str
    name: str | None  # the linked person's name, once someone renames the speaker


class UtteranceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    speaker_id: int
    start_ms: int
    end_ms: int
    text: str


class SummaryOut(BaseModel):
    overview: str
    topics: list[str]


class ActionItemOut(BaseModel):
    id: int
    description: str
    owner: str | None
    due_date: date | None
    due_text: str | None
    status: ActionItemStatus
    evidence: list[int]  # utterance IDs


class DecisionOut(BaseModel):
    id: int
    text: str
    evidence: list[int]  # utterance IDs


class SpeakerRenameIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class ActionItemUpdateIn(BaseModel):
    status: ActionItemStatus


class MeetingDetailOut(MeetingSummaryOut):
    step_timings: dict[str, float]
    error: str | None
    warning: str | None
    language_mode: str
    speakers: list[SpeakerOut]
    utterances: list[UtteranceOut]
    summary: SummaryOut | None
    action_items: list[ActionItemOut]
    decisions: list[DecisionOut]
