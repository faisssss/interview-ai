from sqlalchemy import func, select

from app.db.models import Job, Meeting
from app.pipeline import ingest
from tests.audio_helpers import wav_bytes


def upload(client, data: bytes, name="standup.wav", **form):
    return client.post("/api/meetings", files={"file": (name, data, "audio/wav")}, data=form)


async def test_upload_creates_queued_meeting_and_job(client, db_session, settings):
    response = await upload(client, wav_bytes(2.0))
    assert response.status_code == 201
    body = response.json()
    assert (body["title"], body["status"]) == ("standup", "queued")
    job = (await db_session.execute(select(Job))).scalar_one()
    assert (job.kind, job.payload) == ("process_meeting", {"meeting_id": body["id"]})
    assert (settings.storage_dir / f"meetings/{body['id']}/original.wav").exists()


async def test_upload_uses_given_title(client):
    response = await upload(client, wav_bytes(1.0), title="Weekly sync")
    assert response.json()["title"] == "Weekly sync"


async def test_non_audio_is_rejected_and_nothing_is_kept(client, db_session, settings):
    response = await upload(client, b"hello" * 100, name="notes.txt")
    assert response.status_code == 422
    assert response.json()["detail"] == "This file doesn't contain audio we can read."
    assert await db_session.scalar(select(func.count()).select_from(Meeting)) == 0
    assert not any((settings.storage_dir / "meetings").glob("*/*"))


async def test_recording_over_the_limit_is_rejected(make_client):
    async with make_client(max_duration_minutes=2) as client:
        response = await upload(client, wav_bytes(121.0, rate=8_000))
    assert response.status_code == 422
    assert response.json()["detail"] == "Recordings can be up to 2 minutes long."


async def test_unknown_duration_is_accepted_at_upload(client, monkeypatch):
    monkeypatch.setattr(ingest, "probe_audio", lambda path: ingest.AudioInfo(duration_s=None))
    assert (await upload(client, wav_bytes(1.0))).status_code == 201


async def test_file_over_size_limit_returns_413(make_client):
    async with make_client(max_upload_mb=1) as client:
        response = await upload(client, b"\0" * (2 * 1024 * 1024))
    assert response.status_code == 413
    assert response.json()["detail"] == "Files can be up to 1 MB."


async def test_list_is_newest_first(client):
    first = (await upload(client, wav_bytes(1.0), title="one")).json()["id"]
    second = (await upload(client, wav_bytes(1.0), title="two")).json()["id"]
    assert [m["id"] for m in (await client.get("/api/meetings")).json()] == [second, first]


async def test_detail_of_a_queued_meeting(client):
    meeting_id = (await upload(client, wav_bytes(1.0))).json()["id"]
    body = (await client.get(f"/api/meetings/{meeting_id}")).json()
    assert (body["status"], body["utterances"], body["summary"], body["step_timings"]) == (
        "queued",
        [],
        None,
        {},
    )


async def test_unknown_meeting_is_404(client):
    response = await client.get("/api/meetings/999")
    assert (response.status_code, response.json()["detail"]) == (404, "Meeting not found.")
