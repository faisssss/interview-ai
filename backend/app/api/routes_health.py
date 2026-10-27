from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionDep

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(session: SessionDep) -> dict[str, str]:
    await session.execute(text("select 1"))
    return {"status": "ok", "database": "ok"}
