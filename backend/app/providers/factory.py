"""Choose the model implementations named in settings."""

from app.config import Settings
from app.providers.asr_faster_whisper import FasterWhisperTranscriber
from app.providers.base import Diarizer, Extractor, Providers, Transcriber
from app.providers.diarization_pyannote import PyannoteDiarizer
from app.providers.fake import FakeDiarizer, FakeExtractor, FakeTranscriber
from app.providers.llm_claude import ClaudeExtractor, make_anthropic_client


def build_providers(settings: Settings) -> Providers:
    return Providers(_transcriber(settings), _diarizer(settings), _extractor(settings))


def _transcriber(settings: Settings) -> Transcriber:
    if settings.asr_provider == "fake":
        return FakeTranscriber()
    return FasterWhisperTranscriber(settings.asr_model, settings.ml_device, settings.asr_batch_size)


def _diarizer(settings: Settings) -> Diarizer:
    if settings.diarization_provider == "fake":
        return FakeDiarizer()
    if settings.hf_token is None:
        raise RuntimeError("HF_TOKEN is required for local diarization")
    return PyannoteDiarizer(settings.hf_token.get_secret_value(), settings.ml_device)


def _extractor(settings: Settings) -> Extractor:
    if settings.llm_provider == "fake":
        return FakeExtractor()
    return ClaudeExtractor(
        make_anthropic_client(settings.anthropic_api_key),
        settings.llm_model_extract,
        settings.llm_effort_extract,
    )
