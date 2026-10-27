"""FastAPI application factory. Run with: uv run python -m uvicorn app.api.main:app"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_action_items, routes_health, routes_meetings, routes_speakers
from app.config import Settings, get_settings
from app.db.base import make_engine, make_session_factory
from app.storage import LocalStorage


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Meeting memory assistant", lifespan=_lifespan)
    app.state.settings = settings
    # Created here rather than in the lifespan, so tests that skip lifespan events still work.
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.storage = LocalStorage(settings.storage_dir)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_health.router)
    app.include_router(routes_meetings.router)
    app.include_router(routes_speakers.router)
    app.include_router(routes_action_items.router)
    return app


app = create_app()
