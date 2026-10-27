"""Speaker diarization (who spoke when) on this machine with pyannote.audio (`ml` extra)."""

import wave
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from app.pipeline.types import DiarizationResult, SpeakerTurn
from app.providers.gpu import free_gpu_memory, run_with_cpu_fallback

PIPELINE_NAME = "pyannote/speaker-diarization-community-1"
_SAMPLE_RATE = 16_000


def read_wav_mono(path: Path) -> np.ndarray:
    """A 16-bit mono WAV as float32 samples in [-1, 1]."""
    with wave.open(str(path), "rb") as f:
        pcm = f.readframes(f.getnframes())
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def turns_from_annotation(annotation: Iterable[tuple[Any, str]]) -> list[SpeakerTurn]:
    return [
        SpeakerTurn(
            speaker=speaker, start_ms=round(turn.start * 1000), end_ms=round(turn.end * 1000)
        )
        for turn, speaker in annotation
    ]


def embeddings_by_label(
    labels: Sequence[str], embeddings: np.ndarray | None
) -> dict[str, list[float]]:
    """Pair each speaker label with its voice embedding, skipping all-zero padding rows."""
    if embeddings is None:
        return {}
    return {
        label: [float(x) for x in vector]
        for label, vector in zip(labels, embeddings, strict=False)
        if np.any(vector)
    }


def _labelled_segments(annotation: Any) -> Iterable[tuple[Any, str]]:
    return ((segment, label) for segment, _, label in annotation.itertracks(yield_label=True))


class PyannoteDiarizer:
    def __init__(self, hf_token: str, device: str) -> None:
        self._hf_token = hf_token
        self._device = device

    def diarize(self, wav_path: Path) -> DiarizationResult:
        return run_with_cpu_fallback(lambda device: self._run(device, wav_path), self._device)

    def _run(self, device: str, wav_path: Path) -> DiarizationResult:
        import torch  # pyright: ignore[reportMissingImports]
        from pyannote.audio import Pipeline  # pyright: ignore[reportMissingImports]

        pipeline = Pipeline.from_pretrained(PIPELINE_NAME, token=self._hf_token)
        try:
            pipeline.to(torch.device(device))
            # In-memory audio, so pyannote needs no FFmpeg of its own.
            waveform = torch.from_numpy(read_wav_mono(wav_path)).unsqueeze(0)
            output = pipeline({"waveform": waveform, "sample_rate": _SAMPLE_RATE})
            return DiarizationResult(
                # The "exclusive" version has no overlapping turns, which suits word alignment.
                turns=turns_from_annotation(
                    _labelled_segments(output.exclusive_speaker_diarization)
                ),
                embeddings=embeddings_by_label(
                    output.speaker_diarization.labels(), output.speaker_embeddings
                ),
            )
        finally:
            del pipeline
            free_gpu_memory()
