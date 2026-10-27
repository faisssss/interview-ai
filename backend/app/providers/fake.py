"""Deterministic stand-ins for the real models, used by tests, CI and offline development."""

from app.pipeline.extract import (
    EXTRACTION_PROMPT_VERSION,
    ExtractedActionItem,
    ExtractedDecision,
    Extraction,
    ExtractionOutput,
    ExtractionRequest,
)


class FakeExtractor:
    """Cites the first and last lines. The first fail_times calls raise."""

    def __init__(self, fail_times: int = 0) -> None:
        self.calls = 0
        self._fail_times = fail_times

    def extract(self, request: ExtractionRequest) -> ExtractionOutput:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("fake extraction failure")
        first, last = request.lines[0], request.lines[-1]
        extraction = Extraction(
            summary="Fake summary of the meeting.",
            topics=["Deck"],
            action_items=[
                ExtractedActionItem(
                    description="Send the deck",
                    owner=last.speaker_label,
                    due_text="by Friday",
                    due_date=None,
                    evidence=[last.seq],
                )
            ],
            decisions=[ExtractedDecision(text="Send the deck by Friday", evidence=[first.seq])],
        )
        return ExtractionOutput(
            extraction=extraction, model="fake", prompt_version=EXTRACTION_PROMPT_VERSION
        )
