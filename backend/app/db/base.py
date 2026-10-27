"""Database engine, sessions and the declarative base class."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # Fetch server-side defaults (timestamps, now()) with RETURNING, so async code never
    # triggers a lazy load to read them.
    __mapper_args__ = {"eager_defaults": True}


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def asyncpg_dsn(url: str) -> str:
    """The same URL without SQLAlchemy's driver suffix, for raw asyncpg connections."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)
