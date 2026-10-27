"""Check uploads, decode them to 16 kHz mono WAV, and make a compressed playback copy.

PyAV bundles FFmpeg, so any format FFmpeg reads works, including video files.
"""

import wave
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from av.error import FFmpegError

from app.pipeline.errors import PermanentPipelineError

UNSUPPORTED_MEDIA_MESSAGE = "This file doesn't contain audio we can read."
SAMPLE_RATE = 16_000
_PLAYBACK_CHUNK_SAMPLES = SAMPLE_RATE * 10


class UnsupportedMediaError(PermanentPipelineError):
    def __init__(self) -> None:
        super().__init__(UNSUPPORTED_MEDIA_MESSAGE)


class DurationLimitError(PermanentPipelineError):
    pass


def duration_limit_message(max_minutes: int) -> str:
    return f"Recordings can be up to {max_minutes} minutes long."


@dataclass(frozen=True)
class AudioInfo:
    duration_s: float | None


def probe_audio(path: Path) -> AudioInfo:
    """Read container metadata only. The duration is None when the file doesn't record it."""
    duration: float | None = None
    try:
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise UnsupportedMediaError
            stream = container.streams.audio[0]
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                duration = container.duration / av.time_base
    except FFmpegError as exc:
        raise UnsupportedMediaError from exc
    return AudioInfo(duration)


def decode_to_wav(src: Path, dst: Path) -> float:
    """Decode the first audio stream to 16 kHz mono 16-bit WAV. Returns the duration in seconds."""
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    samples_written = 0
    try:
        with av.open(str(src)) as container, wave.open(str(dst), "wb") as out:
            if not container.streams.audio:
                raise UnsupportedMediaError
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(SAMPLE_RATE)
            for frame in container.decode(container.streams.audio[0]):
                for resampled in resampler.resample(frame):
                    pcm = resampled.to_ndarray()
                    out.writeframes(pcm.tobytes())
                    samples_written += pcm.shape[-1]
            for resampled in resampler.resample(None):
                pcm = resampled.to_ndarray()
                out.writeframes(pcm.tobytes())
                samples_written += pcm.shape[-1]
    except FFmpegError as exc:
        raise UnsupportedMediaError from exc
    return samples_written / SAMPLE_RATE


def encode_playback(src_wav: Path, dst: Path) -> None:
    """Encode a 16 kHz mono WAV as 64 kbit/s AAC in an .m4a file, ten seconds at a time."""
    with wave.open(str(src_wav), "rb") as wav, av.open(str(dst), mode="w") as container:
        rate = wav.getframerate()
        stream = container.add_stream("aac", rate=rate, layout="mono", bit_rate=64_000)
        pts = 0
        while chunk := wav.readframes(_PLAYBACK_CHUNK_SAMPLES):
            samples = np.frombuffer(chunk, dtype="<i2").astype(np.float32) / 32768.0
            frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="fltp", layout="mono")
            frame.sample_rate = rate
            frame.pts = pts
            frame.time_base = Fraction(1, rate)
            pts += samples.size
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
