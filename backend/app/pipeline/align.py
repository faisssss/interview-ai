"""Match transcribed words to speaker turns and group them into utterances."""

from collections.abc import Sequence

from app.pipeline.types import AlignedUtterance, SpeakerTurn, Word

DEFAULT_SPEAKER = "SPEAKER_00"
_SENTENCE_ENDINGS = (".", "?", "!", "।")


def _overlap_ms(word: Word, turn: SpeakerTurn) -> int:
    return min(word.end_ms, turn.end_ms) - max(word.start_ms, turn.start_ms)


def _gap_ms(word: Word, turn: SpeakerTurn) -> int:
    if word.end_ms <= turn.start_ms:
        return turn.start_ms - word.end_ms
    if word.start_ms >= turn.end_ms:
        return word.start_ms - turn.end_ms
    return 0


def assign_speakers(words: Sequence[Word], turns: Sequence[SpeakerTurn]) -> list[str]:
    """Give each word the speaker of the turn it overlaps most, or the nearest turn.

    Ties go to the earlier turn in the list (max/min return the first best item).
    """
    if not turns:
        return [DEFAULT_SPEAKER] * len(words)
    speakers: list[str] = []
    for word in words:
        best = max(turns, key=lambda turn: _overlap_ms(word, turn))
        if _overlap_ms(word, best) <= 0:
            best = min(turns, key=lambda turn: _gap_ms(word, turn))
        speakers.append(best.speaker)
    return speakers


def _utterance(speaker: str, words: list[Word]) -> AlignedUtterance:
    return AlignedUtterance(
        speaker=speaker,
        start_ms=words[0].start_ms,
        end_ms=words[-1].end_ms,
        text="".join(word.text for word in words).strip(),
        words=words,
    )


def group_utterances(
    words: Sequence[Word], speakers: Sequence[str], *, max_pause_ms: int = 1000
) -> list[AlignedUtterance]:
    """Group consecutive words into utterances.

    A new utterance starts when the speaker changes, after a pause longer than
    max_pause_ms, or after a word that ends a sentence.
    """
    utterances: list[AlignedUtterance] = []
    current: list[Word] = []
    current_speaker = DEFAULT_SPEAKER
    for word, speaker in zip(words, speakers, strict=True):
        if current and (
            speaker != current_speaker or word.start_ms - current[-1].end_ms > max_pause_ms
        ):
            utterances.append(_utterance(current_speaker, current))
            current = []
        if not current:
            current_speaker = speaker
        current.append(word)
        if word.text.strip().endswith(_SENTENCE_ENDINGS):
            utterances.append(_utterance(current_speaker, current))
            current = []
    if current:
        utterances.append(_utterance(current_speaker, current))
    return utterances


def label_speakers(utterances: Sequence[AlignedUtterance]) -> dict[str, str]:
    """Map raw diarization labels to "Speaker N", numbered by first appearance."""
    labels: dict[str, str] = {}
    for utterance in utterances:
        if utterance.speaker not in labels:
            labels[utterance.speaker] = f"Speaker {len(labels) + 1}"
    return labels
