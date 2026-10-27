from app.pipeline.align import DEFAULT_SPEAKER, assign_speakers, group_utterances, label_speakers
from app.pipeline.types import AlignedUtterance, SpeakerTurn, Word


def w(text, start, end):
    return Word(text=text, start_ms=start, end_ms=end)


TURNS = [
    SpeakerTurn(speaker="A", start_ms=0, end_ms=1000),
    SpeakerTurn(speaker="B", start_ms=1000, end_ms=3000),
]


def test_word_takes_speaker_with_largest_overlap():
    assert assign_speakers([w(" hi", 800, 1400)], TURNS) == ["B"]


def test_equal_overlap_goes_to_earlier_turn():
    assert assign_speakers([w(" hi", 900, 1100)], TURNS) == ["A"]


def test_word_outside_all_turns_takes_nearest_turn():
    assert assign_speakers([w(" late", 3500, 3700)], TURNS) == ["B"]
    turns = [
        SpeakerTurn(speaker="B", start_ms=500, end_ms=900),
        SpeakerTurn(speaker="A", start_ms=2000, end_ms=3000),
    ]
    assert assign_speakers([w(" early", 0, 100)], turns) == ["B"]


def test_no_turns_gives_default_speaker():
    assert assign_speakers([w(" a", 0, 10)], []) == [DEFAULT_SPEAKER]


def test_splits_on_sentence_end_pause_and_speaker_change():
    words = [
        w(" Hello", 0, 300),
        w(" there.", 300, 600),
        w(" Next", 700, 900),
        w(" one", 900, 1100),
        w(" after", 2200, 2400),
        w(" gap", 2400, 2600),
        w(" Reply", 2600, 2800),
    ]
    utterances = group_utterances(words, ["A"] * 6 + ["B"])
    assert [(u.speaker, u.text, u.start_ms, u.end_ms) for u in utterances] == [
        ("A", "Hello there.", 0, 600),
        ("A", "Next one", 700, 1100),
        ("A", "after gap", 2200, 2600),
        ("B", "Reply", 2600, 2800),
    ]


def test_pause_of_exactly_one_second_does_not_split():
    assert len(group_utterances([w(" a", 0, 100), w(" b", 1100, 1200)], ["A", "A"])) == 1


def test_question_mark_and_danda_end_sentences():
    words = [w(" Ready?", 0, 300), w(" हाँ।", 300, 600), w(" Go", 600, 900)]
    assert [u.text for u in group_utterances(words, ["A", "A", "A"])] == ["Ready?", "हाँ।", "Go"]


def test_empty_input():
    assert group_utterances([], []) == []


def test_speakers_are_numbered_by_first_appearance():
    def u(speaker):
        return AlignedUtterance(speaker=speaker, start_ms=0, end_ms=1, text="x", words=[])

    assert label_speakers([u("SPEAKER_01"), u("SPEAKER_00"), u("SPEAKER_01")]) == {
        "SPEAKER_01": "Speaker 1",
        "SPEAKER_00": "Speaker 2",
    }
