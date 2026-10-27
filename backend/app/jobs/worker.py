"""The background worker: claims queued jobs and runs the pipeline for each.

Run it with:  uv run python -m app.jobs.worker   (Ctrl+C stops it)
"""

import asyncio
import contextlib
import logging
import os
import socket
from datetime import timedelta

import asyncpg

from app.config import get_settings
from app.db.base import asyncpg_dsn, make_engine, make_session_factory
from app.db.models import JobStatus, Meeting
from app.jobs.queue import NOTIFY_CHANNEL, claim_next, complete, fail, heartbeat
from app.pipeline.errors import PermanentPipelineError
from app.pipeline.runner import PipelineContext, mark_meeting_failed, process_meeting
from app.providers.factory import build_providers
from app.storage import LocalStorage

logger = logging.getLogger(__name__)

STOPPED_MESSAGE = "The worker stopped while processing this recording."
UNEXPECTED_MESSAGE = "unexpected error (see the worker log)"


class Worker:
    def __init__(self, ctx: PipelineContext, worker_id: str) -> None:
        self._ctx = ctx
        self._worker_id = worker_id

    async def run_once(self) -> bool:
        """Claim and process one job. Returns False when no job was due."""
        settings = self._ctx.settings
        async with self._ctx.session_factory() as session:
            job = await claim_next(
                session, self._worker_id, stale_after=timedelta(minutes=settings.job_stale_minutes)
            )
            await session.commit()
        if job is None:
            return False

        meeting_id = int(job.payload["meeting_id"])
        if job.attempts > job.max_attempts:  # reclaimed after crashing on its last attempt
            await self._fail(job.id, meeting_id, STOPPED_MESSAGE, retryable=False)
            return True

        logger.info("Job %s: processing meeting %s (attempt %s)", job.id, meeting_id, job.attempts)
        beating = asyncio.create_task(self._heartbeat(job.id))
        try:
            await process_meeting(self._ctx, meeting_id)
        except PermanentPipelineError as exc:
            logger.warning("Job %s failed permanently: %s", job.id, exc)
            await self._fail(job.id, meeting_id, str(exc), retryable=False)
        except Exception as exc:
            logger.exception("Job %s failed", job.id)
            await self._fail(
                job.id, meeting_id, repr(exc), retryable=True, user_message=UNEXPECTED_MESSAGE
            )
        else:
            async with self._ctx.session_factory() as session:
                await complete(session, job.id)
                await session.commit()
            logger.info("Job %s: meeting %s is ready", job.id, meeting_id)
        finally:
            beating.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beating
        return True

    async def _fail(
        self,
        job_id: int,
        meeting_id: int,
        error: str,
        *,
        retryable: bool,
        user_message: str | None = None,
    ) -> None:
        async with self._ctx.session_factory() as session:
            status = await fail(session, job_id, error, retryable=retryable)
            if status == JobStatus.failed:
                meeting = await session.get(Meeting, meeting_id)
                step = meeting.current_step if meeting else None
                await mark_meeting_failed(session, meeting_id, step, user_message or error)
            await session.commit()

    async def _heartbeat(self, job_id: int) -> None:
        while True:
            await asyncio.sleep(self._ctx.settings.heartbeat_seconds)
            async with self._ctx.session_factory() as session:
                await heartbeat(session, job_id)
                await session.commit()

    async def run_forever(self) -> None:
        """Drain due jobs, then sleep until a NOTIFY arrives or the poll interval passes."""
        settings = self._ctx.settings
        connection = await asyncpg.connect(asyncpg_dsn(settings.database_url))
        wake = asyncio.Event()
        await connection.add_listener(NOTIFY_CHANNEL, lambda *_: wake.set())
        logger.info("Worker %s waiting for jobs", self._worker_id)
        try:
            while True:
                wake.clear()
                while await self.run_once():
                    pass
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(wake.wait(), timeout=settings.worker_poll_seconds)
        finally:
            await connection.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    ctx = PipelineContext(
        session_factory=make_session_factory(make_engine(settings.database_url)),
        storage=LocalStorage(settings.storage_dir),
        providers=build_providers(settings),
        settings=settings,
    )
    worker = Worker(ctx, f"{socket.gethostname()}-{os.getpid()}")
    try:
        asyncio.run(worker.run_forever())
    except KeyboardInterrupt:
        logger.info("Worker stopped")


if __name__ == "__main__":
    main()
