import asyncio
from datetime import timedelta

import asyncpg
from sqlalchemy import text

from app.db.base import asyncpg_dsn
from app.db.models import JobStatus
from app.jobs.queue import JOB_PROCESS_MEETING, backoff_seconds, claim_next, enqueue, fail

STALE = timedelta(minutes=10)


def test_backoff_grows_by_four():
    assert [backoff_seconds(n) for n in (1, 2, 3)] == [10, 40, 160]


async def test_claim_returns_oldest_due_job(db_session):
    first = await enqueue(db_session, JOB_PROCESS_MEETING, {"meeting_id": 1}, max_attempts=3)
    await enqueue(db_session, JOB_PROCESS_MEETING, {"meeting_id": 2}, max_attempts=3)
    await db_session.commit()
    job = await claim_next(db_session, "w1", stale_after=STALE)
    assert job is not None and job.id == first.id
    assert (job.status, job.attempts, job.locked_by) == (JobStatus.running, 1, "w1")


async def test_job_scheduled_in_the_future_is_not_claimed(db_session):
    job = await enqueue(db_session, JOB_PROCESS_MEETING, {"meeting_id": 1}, max_attempts=3)
    await db_session.execute(
        text("update jobs set run_after = now() + interval '1 minute' where id = :id"),
        {"id": job.id},
    )
    await db_session.commit()
    assert await claim_next(db_session, "w1", stale_after=STALE) is None


async def test_concurrent_claims_never_return_the_same_job(session_factory):
    async with session_factory() as s:
        await enqueue(s, JOB_PROCESS_MEETING, {"meeting_id": 1}, max_attempts=3)
        await s.commit()
    async with session_factory() as s1, session_factory() as s2:
        first = await claim_next(s1, "w1", stale_after=STALE)  # s1's transaction stays open
        second = await claim_next(s2, "w2", stale_after=STALE)
        assert first is not None and second is None


async def test_stale_running_job_is_reclaimed(db_session):
    job = await enqueue(db_session, JOB_PROCESS_MEETING, {"meeting_id": 1}, max_attempts=3)
    await db_session.execute(
        text(
            "update jobs set status = 'running', attempts = 1, "
            "heartbeat_at = now() - interval '11 minutes' where id = :id"
        ),
        {"id": job.id},
    )
    await db_session.commit()
    reclaimed = await claim_next(db_session, "w2", stale_after=STALE)
    assert reclaimed is not None and (reclaimed.attempts, reclaimed.locked_by) == (2, "w2")


async def test_retryable_failure_requeues_with_backoff(db_session):
    await enqueue(db_session, JOB_PROCESS_MEETING, {"meeting_id": 1}, max_attempts=3)
    await db_session.commit()
    job = await claim_next(db_session, "w1", stale_after=STALE)
    assert job is not None
    assert await fail(db_session, job.id, "boom", retryable=True) == JobStatus.queued
    delay = await db_session.scalar(
        text("select extract(epoch from run_after - now()) from jobs where id = :id"),
        {"id": job.id},
    )
    assert 8 <= delay <= 12


async def test_failure_on_last_attempt_is_final(db_session):
    await enqueue(db_session, JOB_PROCESS_MEETING, {"meeting_id": 1}, max_attempts=1)
    await db_session.commit()
    job = await claim_next(db_session, "w1", stale_after=STALE)
    assert job is not None
    assert await fail(db_session, job.id, "boom", retryable=True) == JobStatus.failed


async def test_permanent_failure_is_not_retried(db_session):
    await enqueue(db_session, JOB_PROCESS_MEETING, {"meeting_id": 1}, max_attempts=3)
    await db_session.commit()
    job = await claim_next(db_session, "w1", stale_after=STALE)
    assert job is not None
    assert await fail(db_session, job.id, "bad file", retryable=False) == JobStatus.failed


async def test_enqueue_notifies_listeners(settings, db_session):
    conn = await asyncpg.connect(asyncpg_dsn(settings.database_url))
    notified = asyncio.Event()
    await conn.add_listener("jobs", lambda *_: notified.set())
    await enqueue(db_session, JOB_PROCESS_MEETING, {"meeting_id": 1}, max_attempts=3)
    await db_session.commit()
    await asyncio.wait_for(notified.wait(), timeout=2)
    await conn.close()
