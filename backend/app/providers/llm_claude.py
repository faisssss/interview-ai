"""Extraction with Claude, using the Anthropic SDK's structured outputs."""

from typing import Literal

import anthropic
from pydantic import SecretStr

from app.pipeline.extract import (
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_SYSTEM_PROMPT,
    Extraction,
    ExtractionError,
    ExtractionOutput,
    ExtractionRefusedError,
    ExtractionRequest,
    ExtractionTruncatedError,
    build_user_message,
)

Effort = Literal["low", "medium", "high", "xhigh", "max"]
_MAX_TOKENS = 16_000
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


def make_anthropic_client(api_key: SecretStr | None) -> anthropic.Anthropic:
    """Use the key from settings when given, else the SDK's own credential lookup."""
    if api_key is not None:
        return anthropic.Anthropic(api_key=api_key.get_secret_value())
    return anthropic.Anthropic()


class ClaudeExtractor:
    def __init__(self, client: anthropic.Anthropic, model: str, effort: Effort) -> None:
        self._client = client
        self._model = model
        self._effort: Effort = effort

    def extract(self, request: ExtractionRequest) -> ExtractionOutput:
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_message(request)}],
            output_format=Extraction,
            output_config={"effort": self._effort},
            # If the request is declined, the API re-runs it on its recommended fallback model.
            extra_headers={"anthropic-beta": _FALLBACK_BETA},
            extra_body={"fallbacks": "default"},
        )
        if response.stop_reason == "refusal":
            raise ExtractionRefusedError
        if response.stop_reason == "max_tokens":
            raise ExtractionTruncatedError
        if response.parsed_output is None:
            raise ExtractionError("The model returned no structured output.")
        return ExtractionOutput(
            extraction=response.parsed_output,
            model=self._model,
            prompt_version=EXTRACTION_PROMPT_VERSION,
        )
