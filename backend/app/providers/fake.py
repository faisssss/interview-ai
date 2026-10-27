"""Deterministic stand-ins for the real models, used by tests, CI and offline development."""

import wave
from collections.abc import Sequence
from pathlib import Path

from app.pipeline.extract import (
    EXTRACTION_PROMPT_VERSION,
    ExtractedActionItem,
    ExtractedDecision,
    Extraction,
    ExtractionOutput,
    ExtractionRequest,
)
from app.pipeline.types import DiarizationResult, SpeakerTurn, TranscriptResult, Word
from app.providers.base import LanguageMode

FAKE_SCRIPT = ("Rahul, can you send the deck by Friday?", "Sure, I will send it tomorrow.")


def _duration_ms(wav_path: Path) -> int:
    with wave.open(str(wav_path), "rb") as f:
        return f.getnframes() * 1000 // f.getframerate()


class FakeTranscriber:
    """Spreads sentence i's words evenly over the i-th equal slice of the recording."""

    def __init__(self, script: Sequence[str] = FAKE_SCRIPT) -> None:
        self.calls = 0
        self._script = tuple(script)

    def transcribe(self, wav_path: Path, language_mode: LanguageMode) -> TranscriptResult:
        self.calls += 1
        words: list[Word] = []
        if self._script:
            slice_ms = _duration_ms(wav_path) // len(self._script)
            for i, sentence in enumerate(self._script):
                tokens = sentence.split()
                step_ms = slice_ms // len(tokens)
                for j, token in enumerate(tokens):
                    start_ms = i * slice_ms + j * step_ms
                    words.append(
                        Word(text=f" {token}", start_ms=start_ms, end_ms=start_ms + step_ms)
                    )
        return TranscriptResult(language="en", words=words)


class FakeDiarizer:
    """Two speakers, one per half of the recording. The first fail_times calls raise."""

    def __init__(self, fail_times: int = 0) -> None:
        self.calls = 0
        self._fail_times = fail_times

    def diarize(self, wav_path: Path) -> DiarizationResult:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("fake diarization failure")
        duration_ms = _duration_ms(wav_path)
        half_ms = duration_ms // 2
        return DiarizationResult(
            turns=[
                SpeakerTurn(speaker="SPEAKER_00", start_ms=0, end_ms=half_ms),
                SpeakerTurn(speaker="SPEAKER_01", start_ms=half_ms, end_ms=duration_ms),
            ],
            embeddings={"SPEAKER_00": [1.0, 0.0, 0.0], "SPEAKER_01": [0.0, 1.0, 0.0]},
        )


class FakeExtractor:
    """Cites the first and last lines. The first fail_times calls raise."""

    def __init__(self, fail_times: int = 0) -> None:
        self.calls = 0
        self._fail_times = fail_times

    def extract(self, request: ExtractionRequest) -> ExtractionOutput:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("fake extraction failure")
        first, last = request.lines[0], request.lines[-1]
        extraction = Extraction(
            summary="Fake summary of the meeting.",
            topics=["Deck"],
            action_items=[
                ExtractedActionItem(
                    description="Send the deck",
                    owner=last.speaker_label,
                    due_text="by Friday",
                    due_date=None,
                    evidence=[last.seq],
                )
            ],
            decisions=[ExtractedDecision(text="Send the deck by Friday", evidence=[first.seq])],
        )
        return ExtractionOutput(
            extraction=extraction, model="fake", prompt_version=EXTRACTION_PROMPT_VERSION
        )
