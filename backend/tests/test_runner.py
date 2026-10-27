import pytest
from sqlalchemy import func, select

from app.db.models import ActionItem, Meeting, Speaker, Summary, Utterance
from app.pipeline.extract import NO_SPEECH_SUMMARY
from app.pipeline.runner import process_meeting
from app.providers.base import Providers
from app.providers.fake import FakeDiarizer, FakeExtractor, FakeTranscriber


async def count(session, model):
    return await session.scalar(select(func.count()).select_from(model))


async def test_meeting_is_processed_end_to_end(make_ctx, uploaded_meeting_id, db_session):
    await process_meeting(make_ctx(), uploaded_meeting_id)
    meeting = await db_session.get(Meeting, uploaded_meeting_id)
    assert meeting is not None
    assert (meeting.status, meeting.current_step) == ("ready", None)
    assert list(meeting.step_timings) == ["ingest", "transcribe", "diarize", "align", "extract"]
    speakers = (await db_session.execute(select(Speaker).order_by(Speaker.id))).scalars().all()
    assert [s.label for s in speakers] == ["Speaker 1", "Speaker 2"]
    assert all(s.voice_embedding is not None for s in speakers)
    texts = (await db_session.execute(select(Utterance.text).order_by(Utterance.seq))).scalars()
    assert list(texts) == [
        "Rahul, can you send the deck by Friday?",
        "Sure, I will send it tomorrow.",
    ]
    item = (await db_session.execute(select(ActionItem))).scalar_one()
    assert item.owner_speaker_id == speakers[1].id
    utterance_ids = set((await db_session.execute(select(Utterance.id))).scalars())
    assert set(item.evidence_utterance_ids) <= utterance_ids


async def test_retry_resumes_after_the_last_finished_step(
    make_ctx, uploaded_meeting_id, db_session
):
    transcriber, diarizer = FakeTranscriber(), FakeDiarizer(fail_times=1)
    ctx = make_ctx(Providers(transcriber, diarizer, FakeExtractor()))
    with pytest.raises(RuntimeError):
        await process_meeting(ctx, uploaded_meeting_id)
    meeting = await db_session.get(Meeting, uploaded_meeting_id)
    assert meeting is not None
    assert list(meeting.step_timings) == ["ingest", "transcribe"]
    await process_meeting(ctx, uploaded_meeting_id)
    assert (transcriber.calls, diarizer.calls) == (1, 2)


async def test_rerunning_align_and_extract_does_not_duplicate_rows(
    make_ctx, uploaded_meeting_id, db_session
):
    ctx = make_ctx()
    await process_meeting(ctx, uploaded_meeting_id)
    meeting = await db_session.get(Meeting, uploaded_meeting_id)
    assert meeting is not None
    meeting.step_timings = {
        k: v for k, v in meeting.step_timings.items() if k not in ("align", "extract")
    }
    await db_session.commit()
    await process_meeting(ctx, uploaded_meeting_id)
    assert (await count(db_session, Utterance), await count(db_session, ActionItem)) == (2, 1)


async def test_silent_recording_needs_no_llm_call(make_ctx, uploaded_meeting_id, db_session):
    extractor = FakeExtractor()
    providers = Providers(FakeTranscriber(script=()), FakeDiarizer(), extractor)
    await process_meeting(make_ctx(providers), uploaded_meeting_id)
    summary = await db_session.get(Summary, uploaded_meeting_id)
    assert summary is not None and summary.overview == NO_SPEECH_SUMMARY
    assert (extractor.calls, await count(db_session, Utterance)) == (0, 0)
