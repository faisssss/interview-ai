import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import Person, Workspace

EXPECTED = {
    "workspaces",
    "meetings",
    "speakers",
    "people",
    "utterances",
    "summaries",
    "action_items",
    "decisions",
    "jobs",
}


async def test_migration_creates_tables_and_local_workspace(db_session):
    result = await db_session.execute(
        text("select tablename from pg_tables where schemaname = 'public'")
    )
    assert set(result.scalars().all()) >= EXPECTED
    workspace = (
        await db_session.execute(select(Workspace).where(Workspace.kind == "local"))
    ).scalar_one()
    assert workspace.name == "Local"


async def test_vector_extension_is_installed(db_session):
    name = await db_session.scalar(
        text("select extname from pg_extension where extname = 'vector'")
    )
    assert name == "vector"


async def test_person_names_are_unique_per_workspace_ignoring_case(db_session, workspace_id):
    db_session.add(Person(workspace_id=workspace_id, name="Asha"))
    await db_session.flush()
    db_session.add(Person(workspace_id=workspace_id, name="asha"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
