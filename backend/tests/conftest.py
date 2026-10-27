"""Shared fixtures: a migrated test database, settings with fake providers, and an API client.

The tests need Postgres from docker compose (`docker compose up -d --wait db`).
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.config import Settings
from app.db.base import asyncpg_dsn, make_engine, make_session_factory
from app.db.models import Workspace

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://meetings:meetings@localhost:5432/meetings_test"
)
# Every table except workspaces, whose seeded row the tests rely on.
TABLES = "jobs, meetings, speakers, people, utterances, summaries, action_items, decisions"


async def _ensure_database(url: str) -> None:
    server, name = asyncpg_dsn(url).rsplit("/", 1)
    conn = await asyncpg.connect(f"{server}/postgres")
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    # Sync on purpose: Alembic's async env.py calls asyncio.run itself.
    asyncio.run(_ensure_database(TEST_DATABASE_URL))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    return TEST_DATABASE_URL


@pytest.fixture
async def clean_database(migrated_database: str) -> AsyncIterator[str]:
    yield migrated_database
    engine = make_engine(migrated_database)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
def settings(clean_database: str, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=clean_database,
        storage_dir=tmp_path / "storage",
        asr_provider="fake",
        diarization_provider="fake",
        llm_provider="fake",
    )


@pytest.fixture
async def session_factory(settings: Settings) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = make_engine(settings.database_url)
    yield make_session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
async def workspace_id(db_session: AsyncSession) -> int:
    return (
        await db_session.execute(select(Workspace.id).where(Workspace.kind == "local"))
    ).scalar_one()


@pytest.fixture
def make_client(settings: Settings):
    """make_client(**overrides) -> async context manager yielding an API client."""

    @asynccontextmanager
    async def factory(**overrides) -> AsyncIterator[AsyncClient]:
        app = create_app(settings.model_copy(update=overrides))
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client
        finally:
            await app.state.engine.dispose()

    return factory


@pytest.fixture
async def client(make_client) -> AsyncIterator[AsyncClient]:
    async with make_client() as api_client:
        yield api_client
