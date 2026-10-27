"""Interfaces for the models the pipeline uses. Each has a local, hosted or fake version."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from app.pipeline.extract import ExtractionOutput, ExtractionRequest
from app.pipeline.types import DiarizationResult, TranscriptResult

LanguageMode = Literal["auto", "en"]


class Transcriber(Protocol):
    def transcribe(self, wav_path: Path, language_mode: LanguageMode) -> TranscriptResult: ...


class Diarizer(Protocol):
    def diarize(self, wav_path: Path) -> DiarizationResult: ...


class Extractor(Protocol):
    def extract(self, request: ExtractionRequest) -> ExtractionOutput: ...


@dataclass(frozen=True)
class Providers:
    transcriber: Transcriber
    diarizer: Diarizer
    extractor: Extractor
