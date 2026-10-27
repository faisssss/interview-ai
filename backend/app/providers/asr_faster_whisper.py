"""Speech-to-text on this machine with faster-whisper (needs the `ml` extra)."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.pipeline.types import TranscriptResult, Word
from app.providers.base import LanguageMode
from app.providers.gpu import free_gpu_memory, run_with_cpu_fallback


def words_from_segments(segments: Iterable[Any]) -> list[Word]:
    """Flatten faster-whisper segments into words with millisecond timings."""
    words: list[Word] = []
    for segment in segments:
        for word in segment.words or []:
            words.append(
                Word(
                    text=word.word,
                    start_ms=round(word.start * 1000),
                    end_ms=round(word.end * 1000),
                    probability=word.probability,
                )
            )
    return words


class FasterWhisperTranscriber:
    def __init__(self, model_name: str, device: str, batch_size: int) -> None:
        self._model_name = model_name
        self._device = device
        self._batch_size = batch_size

    def transcribe(self, wav_path: Path, language_mode: LanguageMode) -> TranscriptResult:
        return run_with_cpu_fallback(
            lambda device: self._run(device, wav_path, language_mode), self._device
        )

    def _run(self, device: str, wav_path: Path, language_mode: LanguageMode) -> TranscriptResult:
        # Importing torch first loads the CUDA cuBLAS/cuDNN DLLs ctranslate2 needs on Windows.
        import torch  # noqa: F401  # pyright: ignore[reportMissingImports]
        from faster_whisper import (  # pyright: ignore[reportMissingImports]
            BatchedInferencePipeline,
            WhisperModel,
        )

        compute_type = "int8_float16" if device == "cuda" else "int8"
        model = WhisperModel(self._model_name, device=device, compute_type=compute_type)
        try:
            segments, info = BatchedInferencePipeline(model).transcribe(
                str(wav_path),
                language=None if language_mode == "auto" else "en",
                word_timestamps=True,
                vad_filter=True,
                batch_size=self._batch_size,
            )
            words = words_from_segments(segments)  # segments is lazy; this runs the model
            return TranscriptResult(language=info.language, words=words)
        finally:
            del model
            free_gpu_memory()
