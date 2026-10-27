"""Manual check that the local GPU models load and run.

Run from backend/ after `uv sync --extra ml`:  uv run python -m scripts.gpu_check
"""

import tempfile
import time
from pathlib import Path

from app.config import get_settings
from app.providers.asr_faster_whisper import FasterWhisperTranscriber
from app.providers.diarization_pyannote import PyannoteDiarizer
from tests.audio_helpers import wav_bytes


def main() -> None:
    import ctranslate2  # pyright: ignore[reportMissingImports]
    import torch  # pyright: ignore[reportMissingImports]

    print("torch", torch.__version__)
    print("cuda available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("gpu:", torch.cuda.get_device_name(0))
    print("ctranslate2 cuda devices:", ctranslate2.get_cuda_device_count())

    settings = get_settings()
    with tempfile.TemporaryDirectory() as folder:
        tone = Path(folder) / "tone.wav"
        tone.write_bytes(wav_bytes(10.0))

        started = time.perf_counter()
        transcriber = FasterWhisperTranscriber(settings.asr_model, "cuda", settings.asr_batch_size)
        transcriber.transcribe(tone, "auto")
        print(f"faster-whisper ({settings.asr_model}): {time.perf_counter() - started:.1f}s")

        if settings.hf_token is None:
            print("pyannote: skipped (set HF_TOKEN in backend/.env)")
            return
        started = time.perf_counter()
        PyannoteDiarizer(settings.hf_token.get_secret_value(), "cuda").diarize(tone)
        print(f"pyannote: {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
