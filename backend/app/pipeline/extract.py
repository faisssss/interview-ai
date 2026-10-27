"""Prompt, response schema and validation for the summary, action items and decisions."""

from collections.abc import Mapping
from datetime import date

from pydantic import BaseModel

from app.pipeline.errors import PermanentPipelineError

EXTRACTION_PROMPT_VERSION = "extract-v1"
NO_SPEECH_SUMMARY = "No speech was detected in this recording."
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

EXTRACTION_SYSTEM_PROMPT = """\
You extract structured notes from a meeting transcript.

Each transcript line looks like: [seq] (hh:mm:ss) Speaker N: text
The user message starts with the meeting date.

Return:
- summary: 3 to 6 sentences in English on what the meeting covered and what came out of it.
- topics: 2 to 8 short topic labels in English.
- action_items: tasks someone agreed to do or was asked to do. description is a short \
imperative sentence in English. owner is the speaker label exactly as written in the \
transcript (for example "Speaker 2") when a speaker owns the task; otherwise the person's \
or group's name as spoken; null if nobody owns it. due_text is the deadline as spoken, or \
null. due_date is that deadline as YYYY-MM-DD, worked out from the meeting date, or null if \
there is none or it is unclear.
- decisions: things the group agreed on, as short statements in English.

Every action item and decision lists in evidence the seq numbers of the lines that support \
it. Use only seq numbers that appear in the transcript. Leave out anything the transcript \
does not support. Write in English even when speakers mix Hindi and English, and keep names \
as spoken."""


class ExtractedActionItem(BaseModel):
    description: str
    owner: str | None
    due_text: str | None
    # Text, not a date: an impossible date from the model must not fail the whole extraction.
    due_date: str | None
    evidence: list[int]


class ExtractedDecision(BaseModel):
    text: str
    evidence: list[int]


class Extraction(BaseModel):
    summary: str
    topics: list[str]
    action_items: list[ExtractedActionItem]
    decisions: list[ExtractedDecision]


class TranscriptLine(BaseModel):
    seq: int
    speaker_label: str
    start_ms: int
    text: str


class ExtractionRequest(BaseModel):
    meeting_date: date
    lines: list[TranscriptLine]


class ExtractionOutput(BaseModel):
    extraction: Extraction
    model: str
    prompt_version: str


class ExtractionError(Exception):
    """The model returned nothing usable. Retrying may help."""


class ExtractionRefusedError(PermanentPipelineError):
    def __init__(self) -> None:
        super().__init__("The model declined to summarise this meeting.")


class ExtractionTruncatedError(PermanentPipelineError):
    def __init__(self) -> None:
        super().__init__("The meeting was too long to summarise in one pass.")


def format_timestamp(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def build_user_message(request: ExtractionRequest) -> str:
    day = request.meeting_date
    lines = "\n".join(
        f"[{line.seq}] ({format_timestamp(line.start_ms)}) {line.speaker_label}: {line.text}"
        for line in request.lines
    )
    return f"Meeting date: {day.isoformat()} ({_WEEKDAYS[day.weekday()]})\n\nTranscript:\n{lines}"


def validate_evidence(extraction: Extraction, valid_seqs: set[int]) -> Extraction:
    """Drop evidence that cites lines not in the transcript, then items left with none."""

    def known(evidence: list[int]) -> list[int]:
        return [seq for seq in evidence if seq in valid_seqs]

    action_items = [
        item.model_copy(update={"evidence": evidence})
        for item in extraction.action_items
        if (evidence := known(item.evidence))
    ]
    decisions = [
        decision.model_copy(update={"evidence": evidence})
        for decision in extraction.decisions
        if (evidence := known(decision.evidence))
    ]
    return extraction.model_copy(update={"action_items": action_items, "decisions": decisions})


def parse_due_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def resolve_owner(
    owner: str | None, speaker_ids_by_label: Mapping[str, int]
) -> tuple[int | None, str | None]:
    """Return (owner_speaker_id, owner_text): a speaker label maps to that speaker."""
    if owner is None or not owner.strip():
        return None, None
    name = owner.strip()
    by_label = {label.lower(): speaker_id for label, speaker_id in speaker_ids_by_label.items()}
    speaker_id = by_label.get(name.lower())
    if speaker_id is not None:
        return speaker_id, None
    return None, name
