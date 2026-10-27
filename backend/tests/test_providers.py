from types import SimpleNamespace as NS

import numpy as np
import pytest

from app.config import Settings
from app.pipeline.types import SpeakerTurn, Word
from app.providers.asr_faster_whisper import words_from_segments
from app.providers.diarization_pyannote import embeddings_by_label, turns_from_annotation
from app.providers.factory import build_providers
from app.providers.fake import FakeDiarizer, FakeExtractor, FakeTranscriber
from app.providers.gpu import run_with_cpu_fallback
from tests.audio_helpers import wav_bytes


def test_words_from_segments_converts_seconds_to_ms():
    segments = [
        NS(words=[NS(word=" Hello", start=0.5, end=0.92, probability=0.9)]),
        NS(words=None),
    ]
    assert words_from_segments(segments) == [
        Word(text=" Hello", start_ms=500, end_ms=920, probability=0.9)
    ]


def test_turns_from_annotation():
    annotation = [(NS(start=0.0, end=1.25), "SPEAKER_00"), (NS(start=1.25, end=2.0), "SPEAKER_01")]
    assert turns_from_annotation(annotation) == [
        SpeakerTurn(speaker="SPEAKER_00", start_ms=0, end_ms=1250),
        SpeakerTurn(speaker="SPEAKER_01", start_ms=1250, end_ms=2000),
    ]


def test_embeddings_skip_zero_padding():
    array = np.array([[0.1, 0.2], [0.0, 0.0]], dtype=np.float32)
    assert embeddings_by_label(["SPEAKER_00", "SPEAKER_01"], array) == {
        "SPEAKER_00": pytest.approx([0.1, 0.2])
    }
    assert embeddings_by_label(["SPEAKER_00"], None) == {}


def test_out_of_memory_falls_back_to_cpu():
    calls = []

    def run(device):
        calls.append(device)
        if device == "cuda":
            raise RuntimeError("CUDA failed with error out of memory")
        return "ok"

    assert run_with_cpu_fallback(run, "cuda") == "ok"
    assert calls == ["cuda", "cpu"]


def test_other_errors_are_not_retried_on_cpu():
    calls = []

    def run(device):
        calls.append(device)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_with_cpu_fallback(run, "cuda")
    assert calls == ["cuda"]


def test_fake_transcriber_puts_one_sentence_in_each_half(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(wav_bytes(4.0))
    words = FakeTranscriber().transcribe(wav, "auto").words
    first = [x for x in words if x.end_ms <= 2000]
    assert "".join(x.text for x in first).strip() == "Rahul, can you send the deck by Friday?"
    assert words[-1].end_ms <= 4000


def test_fake_transcriber_can_be_silent(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(wav_bytes(1.0))
    assert FakeTranscriber(script=()).transcribe(wav, "auto").words == []


def test_fake_diarizer_splits_the_recording_in_half(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(wav_bytes(4.0))
    result = FakeDiarizer().diarize(wav)
    assert [(t.speaker, t.start_ms, t.end_ms) for t in result.turns] == [
        ("SPEAKER_00", 0, 2000),
        ("SPEAKER_01", 2000, 4000),
    ]


def test_fake_settings_build_fake_providers():
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        asr_provider="fake",
        diarization_provider="fake",
        llm_provider="fake",
    )
    providers = build_providers(settings)
    assert isinstance(providers.transcriber, FakeTranscriber)
    assert isinstance(providers.diarizer, FakeDiarizer)
    assert isinstance(providers.extractor, FakeExtractor)


def test_local_diarization_needs_a_hugging_face_token():
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        asr_provider="fake",
        diarization_provider="local",
        llm_provider="fake",
    )
    with pytest.raises(RuntimeError, match="HF_TOKEN is required for local diarization"):
        build_providers(settings)
