from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import anthropic
import pytest

from app.pipeline.extract import (
    EXTRACTION_SYSTEM_PROMPT,
    Extraction,
    ExtractionError,
    ExtractionRefusedError,
    ExtractionRequest,
    ExtractionTruncatedError,
    TranscriptLine,
    build_user_message,
    parse_due_date,
    validate_evidence,
)
from app.providers.llm_claude import ClaudeExtractor

REQUEST = ExtractionRequest(
    meeting_date=date(2026, 10, 26),
    lines=[
        TranscriptLine(
            seq=0, speaker_label="Speaker 1", start_ms=0, text="Rahul, send the deck by Friday."
        )
    ],
)
PARSED = Extraction(summary="s", topics=["t"], action_items=[], decisions=[])


class StubMessages:
    def __init__(self, stop_reason="end_turn", parsed=PARSED):
        self.calls, self.stop_reason, self.parsed = [], stop_reason, parsed

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=self.parsed)


def extractor(messages):
    client = cast(anthropic.Anthropic, SimpleNamespace(messages=messages))
    return ClaudeExtractor(client, model="claude-opus-5-5", effort="medium")


def test_request_shape():
    messages = StubMessages()
    out = extractor(messages).extract(REQUEST)
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["system"] == EXTRACTION_SYSTEM_PROMPT
    assert call["messages"] == [{"role": "user", "content": build_user_message(REQUEST)}]
    assert call["output_format"] is Extraction
    assert call["output_config"] == {"effort": "medium"}
    assert call["max_tokens"] == 16_000
    assert call["extra_headers"] == {"anthropic-beta": "server-side-fallback-2026-07-01"}
    assert call["extra_body"] == {"fallbacks": "default"}
    assert (out.extraction, out.model, out.prompt_version) == (
        PARSED,
        "claude-opus-5-5",
        "extract-v1",
    )


@pytest.mark.parametrize(
    ("stop_reason", "parsed", "error"),
    [
        ("refusal", None, ExtractionRefusedError),
        ("max_tokens", None, ExtractionTruncatedError),
        ("end_turn", None, ExtractionError),
    ],
)
def test_unusable_responses_raise(stop_reason, parsed, error):
    with pytest.raises(error):
        extractor(StubMessages(stop_reason, parsed)).extract(REQUEST)


def test_recorded_extraction_is_validated():
    # A realistic model output written in the response schema: one action item cites a
    # line that doesn't exist (seq 999) and one has an impossible due date.
    extraction = Extraction.model_validate_json(
        (Path(__file__).parent / "fixtures" / "extraction_sample.json").read_text(encoding="utf-8")
    )
    valid = validate_evidence(extraction, valid_seqs={0, 1, 2, 3})
    assert len(valid.action_items) == len(extraction.action_items) - 1
    assert [parse_due_date(a.due_date) for a in valid.action_items].count(None) >= 1


@pytest.mark.paid
def test_real_claude_extraction():
    from app.config import get_settings
    from app.providers.llm_claude import make_anthropic_client

    settings = get_settings()
    lines = [
        TranscriptLine(seq=i, speaker_label=speaker, start_ms=i * 3000, text=text)
        for i, (speaker, text) in enumerate(
            [
                ("Speaker 1", "Rahul, can you send the pricing deck by Friday?"),
                ("Speaker 2", "Yes, I'll send it by Friday."),
                ("Speaker 1", "Great. And we're keeping the launch on the 15th."),
                ("Speaker 2", "Agreed, the 15th it is."),
            ]
        )
    ]
    out = ClaudeExtractor(
        make_anthropic_client(settings.anthropic_api_key),
        settings.llm_model_extract,
        settings.llm_effort_extract,
    ).extract(ExtractionRequest(meeting_date=date(2026, 10, 26), lines=lines))
    assert out.extraction.action_items and out.extraction.decisions
    for entry in out.extraction.action_items + out.extraction.decisions:
        assert set(entry.evidence) <= {0, 1, 2, 3}
