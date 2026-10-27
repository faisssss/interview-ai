"""A small job queue in Postgres.

Workers claim jobs with SELECT ... FOR UPDATE SKIP LOCKED, so two workers never get the same
job, and LISTEN/NOTIFY wakes idle workers as soon as a job arrives. None of these functions
commit: the caller owns the transaction.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, JobStatus

JOB_PROCESS_MEETING = "process_meeting"
NOTIFY_CHANNEL = "jobs"
_MAX_ERROR_CHARS = 2000

# Claims the oldest due job, or one whose worker stopped sending heartbeats.
_CLAIM_SQL = text(
    """
    UPDATE jobs
    SET status = 'running', locked_by = :worker_id, heartbeat_at = now(),
        attempts = attempts + 1, updated_at = now()
    WHERE id = (
        SELECT id FROM jobs
        WHERE (status = 'queued' AND run_after <= now())
           OR (status = 'running' AND heartbeat_at < now() - CAST(:stale_after AS interval))
        ORDER BY run_after, id
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *
    """
)


def backoff_seconds(attempts: int) -> int:
    """Delay before the next attempt: 10 s, 40 s, 160 s, ..."""
    return 10 * 4 ** (attempts - 1)


async def enqueue(
    session: AsyncSession, kind: str, payload: dict[str, Any], *, max_attempts: int
) -> Job:
    job = Job(kind=kind, payload=payload, max_attempts=max_attempts)
    session.add(job)
    await session.flush()
    # Delivered when the transaction commits, so workers never see an uncommitted job.
    await session.execute(text("SELECT pg_notify(:channel, '')"), {"channel": NOTIFY_CHANNEL})
    return job


async def claim_next(
    session: AsyncSession, worker_id: str, *, stale_after: timedelta
) -> Job | None:
    statement = (
        select(Job)
        .from_statement(_CLAIM_SQL)
        # The session may already hold this job from enqueue(); load the claimed values.
        .execution_options(populate_existing=True)
    )
    result = await session.execute(statement, {"worker_id": worker_id, "stale_after": stale_after})
    return result.scalar_one_or_none()


async def heartbeat(session: AsyncSession, job_id: int) -> None:
    await session.execute(update(Job).where(Job.id == job_id).values(heartbeat_at=func.now()))


async def complete(session: AsyncSession, job_id: int) -> None:
    await session.execute(
        update(Job).where(Job.id == job_id).values(status=JobStatus.done, locked_by=None)
    )


async def fail(session: AsyncSession, job_id: int, error: str, *, retryable: bool) -> JobStatus:
    """Requeue the job with a backoff if it may run again; otherwise mark it failed."""
    attempts, max_attempts = (
        await session.execute(select(Job.attempts, Job.max_attempts).where(Job.id == job_id))
    ).one()
    values: dict[str, Any] = {"last_error": error[:_MAX_ERROR_CHARS], "locked_by": None}
    if retryable and attempts < max_attempts:
        status = JobStatus.queued
        values["run_after"] = func.now() + timedelta(seconds=backoff_seconds(attempts))
    else:
        status = JobStatus.failed
    await session.execute(update(Job).where(Job.id == job_id).values(status=status, **values))
    return status
