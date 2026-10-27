"""Request dependencies: database session and the current workspace."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workspace


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_workspace_id(session: SessionDep) -> int:
    """The single local workspace (hosted sandboxes come in a later phase)."""
    workspace_id = await session.scalar(
        select(Workspace.id).where(Workspace.kind == "local").order_by(Workspace.id).limit(1)
    )
    if workspace_id is None:
        raise RuntimeError("The local workspace is missing; run the database migrations.")
    return workspace_id


WorkspaceDep = Annotated[int, Depends(get_workspace_id)]
