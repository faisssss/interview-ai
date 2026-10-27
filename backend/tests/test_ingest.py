import shutil
import wave

import pytest

from app.pipeline.ingest import (
    UNSUPPORTED_MEDIA_MESSAGE,
    UnsupportedMediaError,
    decode_to_wav,
    encode_playback,
    probe_audio,
)
from tests.audio_helpers import write_tone_wav, write_video_mp4


def test_probe_reports_duration(tmp_path):
    src = write_tone_wav(tmp_path / "a.wav", 3.0)
    assert probe_audio(src).duration_s == pytest.approx(3.0, abs=0.05)


def test_decode_produces_16k_mono_pcm(tmp_path):
    src = write_tone_wav(tmp_path / "a.wav", 3.0, rate=44_100, channels=2)
    duration = decode_to_wav(src, tmp_path / "out.wav")
    with wave.open(str(tmp_path / "out.wav")) as f:
        assert (f.getframerate(), f.getnchannels(), f.getsampwidth()) == (16_000, 1, 2)
        assert f.getnframes() == pytest.approx(48_000, abs=800)
    assert duration == pytest.approx(3.0, abs=0.05)


def test_playback_copy_is_playable_m4a(tmp_path):
    wav = tmp_path / "out.wav"
    decode_to_wav(write_tone_wav(tmp_path / "a.wav", 3.0), wav)
    encode_playback(wav, tmp_path / "playback.m4a")
    assert probe_audio(tmp_path / "playback.m4a").duration_s == pytest.approx(3.0, abs=0.1)


def test_audio_is_taken_from_a_video_file(tmp_path):
    src = write_video_mp4(tmp_path / "screen.mp4", 2.0)
    assert decode_to_wav(src, tmp_path / "out.wav") == pytest.approx(2.0, abs=0.1)


def test_file_without_extension_is_recognised_by_content(tmp_path):
    src = tmp_path / "recording"
    shutil.copy(write_tone_wav(tmp_path / "a.wav", 1.0), src)
    assert probe_audio(src).duration_s == pytest.approx(1.0, abs=0.05)


def test_garbage_is_rejected(tmp_path):
    bad = tmp_path / "notes.mp3"
    bad.write_bytes(b"not audio at all" * 100)
    with pytest.raises(UnsupportedMediaError, match=UNSUPPORTED_MEDIA_MESSAGE):
        probe_audio(bad)


def test_video_without_audio_is_rejected(tmp_path):
    with pytest.raises(UnsupportedMediaError):
        probe_audio(write_video_mp4(tmp_path / "silent.mp4", 1.0, with_audio=False))
