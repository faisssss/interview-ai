"""Generate small audio and video files for tests, so no binary fixtures live in the repo."""

import io
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np


def _tone(seconds: float, rate: int) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def _pcm16(samples: np.ndarray, channels: int) -> bytes:
    pcm = (samples * 32767).astype("<i2")
    return np.repeat(pcm[:, None], channels, axis=1).tobytes()


def wav_bytes(seconds: float, *, rate: int = 16_000) -> bytes:
    """A mono 16-bit WAV file of a 440 Hz tone, as bytes."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(_pcm16(_tone(seconds, rate), 1))
    return buffer.getvalue()


def write_tone_wav(path: Path, seconds: float, *, rate: int = 44_100, channels: int = 2) -> Path:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(_pcm16(_tone(seconds, rate), channels))
    return path


def write_video_mp4(path: Path, seconds: float, *, with_audio: bool = True) -> Path:
    """A tiny MP4: mpeg4 video (64x64, 10 fps) plus an AAC tone when with_audio."""
    fps, rate = 10, 44_100
    with av.open(str(path), mode="w") as container:
        # Every stream must exist before the first packet is muxed.
        video = container.add_stream("mpeg4", rate=fps)
        video.width, video.height, video.pix_fmt = 64, 64, "yuv420p"
        audio = container.add_stream("aac", rate=rate, layout="mono") if with_audio else None
        for i in range(int(seconds * fps)):
            image = np.full((64, 64, 3), (i * 20) % 255, dtype=np.uint8)
            for packet in video.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                container.mux(packet)
        for packet in video.encode(None):
            container.mux(packet)
        if audio is not None:
            frame = av.AudioFrame.from_ndarray(
                _tone(seconds, rate).reshape(1, -1), format="fltp", layout="mono"
            )
            frame.sample_rate = rate
            frame.pts = 0
            frame.time_base = Fraction(1, rate)
            for packet in audio.encode(frame):
                container.mux(packet)
            for packet in audio.encode(None):
                container.mux(packet)
    return path
