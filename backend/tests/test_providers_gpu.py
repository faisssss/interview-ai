import pytest

from app.config import get_settings
from app.pipeline.types import DiarizationResult, TranscriptResult
from app.providers.asr_faster_whisper import FasterWhisperTranscriber
from app.providers.diarization_pyannote import PyannoteDiarizer
from tests.audio_helpers import wav_bytes

pytestmark = pytest.mark.gpu


@pytest.fixture
def tone(tmp_path):
    path = tmp_path / "tone.wav"
    path.write_bytes(wav_bytes(10.0))
    return path


def test_faster_whisper_runs_on_gpu(tone):
    s = get_settings()
    result = FasterWhisperTranscriber(s.asr_model, "cuda", s.asr_batch_size).transcribe(
        tone, "auto"
    )
    assert isinstance(result, TranscriptResult)


def test_pyannote_runs_on_gpu(tone):
    token = get_settings().hf_token
    assert token is not None, "set HF_TOKEN in backend/.env"
    diarizer = PyannoteDiarizer(token.get_secret_value(), "cuda")
    assert isinstance(diarizer.diarize(tone), DiarizationResult)
