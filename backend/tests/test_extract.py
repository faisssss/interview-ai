from datetime import date

from app.pipeline.extract import (
    ExtractedActionItem,
    ExtractedDecision,
    Extraction,
    ExtractionRequest,
    TranscriptLine,
    build_user_message,
    format_timestamp,
    parse_due_date,
    resolve_owner,
    validate_evidence,
)
from app.providers.fake import FakeExtractor


def item(evidence):
    return ExtractedActionItem(
        description="d", owner=None, due_text=None, due_date=None, evidence=evidence
    )


def test_format_timestamp():
    assert (format_timestamp(134_000), format_timestamp(3_723_000)) == ("00:02:14", "01:02:03")


def test_user_message_layout():
    request = ExtractionRequest(
        meeting_date=date(2026, 10, 26),
        lines=[
            TranscriptLine(
                seq=0, speaker_label="Speaker 1", start_ms=134_000, text="Launch is on the 15th."
            )
        ],
    )
    assert build_user_message(request) == (
        "Meeting date: 2026-10-26 (Monday)\n\nTranscript:\n"
        "[0] (00:02:14) Speaker 1: Launch is on the 15th."
    )


def test_evidence_is_filtered_and_unsupported_items_dropped():
    extraction = Extraction(
        summary="s",
        topics=[],
        action_items=[item([3, 999]), item([999]), item([])],
        decisions=[
            ExtractedDecision(text="a", evidence=[1]),
            ExtractedDecision(text="b", evidence=[42]),
        ],
    )
    out = validate_evidence(extraction, valid_seqs={1, 3})
    assert [a.evidence for a in out.action_items] == [[3]]
    assert [d.text for d in out.decisions] == ["a"]


def test_due_dates_are_parsed_leniently():
    assert parse_due_date("2026-10-30") == date(2026, 10, 30)
    assert parse_due_date("2026-02-30") is None
    assert parse_due_date("next sprint") is None
    assert parse_due_date(None) is None


def test_owner_resolution():
    ids = {"Speaker 1": 10, "Speaker 2": 11}
    assert resolve_owner("Speaker 2", ids) == (11, None)
    assert resolve_owner("speaker 2", ids) == (11, None)
    assert resolve_owner("Rahul", ids) == (None, "Rahul")
    assert resolve_owner("Speaker 7", ids) == (None, "Speaker 7")
    assert resolve_owner("  ", ids) == (None, None)
    assert resolve_owner(None, ids) == (None, None)


def test_fake_extractor_is_deterministic_and_cites_real_lines():
    request = ExtractionRequest(
        meeting_date=date(2026, 10, 26),
        lines=[
            TranscriptLine(
                seq=0, speaker_label="Speaker 1", start_ms=0, text="Can you send the deck?"
            ),
            TranscriptLine(seq=1, speaker_label="Speaker 2", start_ms=2000, text="Sure."),
        ],
    )
    out = FakeExtractor().extract(request)
    assert out.extraction.action_items[0].owner == "Speaker 2"
    assert out.extraction.action_items[0].evidence == [1]
    assert out.extraction.decisions[0].evidence == [0]
    assert (out.model, out.prompt_version) == ("fake", "extract-v1")
