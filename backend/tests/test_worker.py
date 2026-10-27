from sqlalchemy import select, text

from app.db.models import Job, Meeting, Utterance
from app.jobs.worker import Worker
from app.pipeline.runner import EXTRACTION_WARNING
from app.providers.base import Providers
from app.providers.fake import FakeDiarizer, FakeExtractor, FakeTranscriber


async def test_worker_processes_a_queued_job(make_ctx, uploaded_meeting_id, db_session):
    worker = Worker(make_ctx(), "w1")
    assert await worker.run_once() is True
    assert await worker.run_once() is False
    job = (await db_session.execute(select(Job))).scalar_one()
    meeting = await db_session.get(Meeting, uploaded_meeting_id)
    assert meeting is not None
    assert (job.status, meeting.status) == ("done", "ready")


async def test_unreadable_file_fails_once_with_a_clear_message(
    make_ctx, uploaded_meeting_id, db_session, settings
):
    original = settings.storage_dir / f"meetings/{uploaded_meeting_id}/original.wav"
    original.write_bytes(b"broken" * 100)
    await Worker(make_ctx(), "w1").run_once()
    job = (await db_session.execute(select(Job))).scalar_one()
    meeting = await db_session.get(Meeting, uploaded_meeting_id)
    assert meeting is not None
    assert (job.status, job.attempts) == ("failed", 1)
    assert (meeting.status, meeting.error) == (
        "failed",
        "Failed at ingest: This file doesn't contain audio we can read.",
    )


async def test_recording_over_the_limit_found_at_ingest_is_not_retried(
    make_ctx, uploaded_meeting_id, db_session
):
    await Worker(make_ctx(max_duration_minutes=0), "w1").run_once()
    meeting = await db_session.get(Meeting, uploaded_meeting_id)
    assert meeting is not None
    assert (meeting.status, meeting.error) == (
        "failed",
        "Failed at ingest: Recordings can be up to 0 minutes long.",
    )


async def test_transient_failure_is_requeued(make_ctx, uploaded_meeting_id, db_session):
    ctx = make_ctx(Providers(FakeTranscriber(), FakeDiarizer(fail_times=1), FakeExtractor()))
    await Worker(ctx, "w1").run_once()
    job = (await db_session.execute(select(Job))).scalar_one()
    meeting = await db_session.get(Meeting, uploaded_meeting_id)
    assert meeting is not None
    assert (job.status, job.attempts, meeting.status) == ("queued", 1, "processing")


async def test_extraction_that_keeps_failing_leaves_a_usable_meeting(
    make_ctx, uploaded_meeting_id, db_session
):
    providers = Providers(FakeTranscriber(), FakeDiarizer(), FakeExtractor(fail_times=99))
    worker = Worker(make_ctx(providers), "w1")
    for _ in range(3):
        await db_session.execute(text("update jobs set run_after = now()"))
        await db_session.commit()
        await worker.run_once()
    meeting = await db_session.get(Meeting, uploaded_meeting_id)
    assert meeting is not None
    await db_session.refresh(meeting)
    assert (meeting.status, meeting.warning) == ("ready", EXTRACTION_WARNING)
    assert len((await db_session.execute(select(Utterance))).scalars().all()) == 2
