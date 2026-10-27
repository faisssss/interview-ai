"""Tick off (or reopen, or drop) an action item."""

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep, WorkspaceDep
from app.api.routes_meetings import action_item_out, speakers_with_names
from app.api.schemas import ActionItemOut, ActionItemUpdateIn
from app.db.models import ActionItem

router = APIRouter(prefix="/api")


@router.patch("/action-items/{item_id}")
async def update_action_item(
    item_id: int, body: ActionItemUpdateIn, session: SessionDep, workspace_id: WorkspaceDep
) -> ActionItemOut:
    item = await session.get(ActionItem, item_id)
    if item is None or item.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Action item not found.")
    item.status = body.status
    await session.commit()
    display_names = {
        speaker.id: name or speaker.label
        for speaker, name in await speakers_with_names(session, item.meeting_id)
    }
    return action_item_out(item, display_names)
