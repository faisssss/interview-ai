"""Data passed between pipeline steps. Each model is also stored as a JSON artifact."""

from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Word(_Frozen):
    text: str  # as transcribed, usually with a leading space
    start_ms: int
    end_ms: int
    probability: float | None = None


class TranscriptResult(_Frozen):
    language: str
    words: list[Word]


class SpeakerTurn(_Frozen):
    speaker: str  # diarization label, e.g. "SPEAKER_00"
    start_ms: int
    end_ms: int


class DiarizationResult(_Frozen):
    turns: list[SpeakerTurn]
    embeddings: dict[str, list[float]]  # voice embedding per speaker label


class AlignedUtterance(_Frozen):
    speaker: str
    start_ms: int
    end_ms: int
    text: str
    words: list[Word]
