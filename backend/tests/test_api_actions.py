import json

from sqlalchemy import func, select

from app.api.export_openapi import main as export_openapi
from app.db.models import Job, Meeting, Person


async def test_audio_supports_range_requests(client, processed_meeting_id):
    response = await client.get(
        f"/api/meetings/{processed_meeting_id}/audio", headers={"Range": "bytes=0-99"}
    )
    assert response.status_code == 206
    assert response.headers["content-range"].startswith("bytes 0-99/")
    assert len(response.content) == 100


async def test_audio_is_404_before_processing(client, uploaded_meeting_id):
    response = await client.get(f"/api/meetings/{uploaded_meeting_id}/audio")
    assert (response.status_code, response.json()["detail"]) == (404, "Audio is not ready yet.")


async def test_failed_meeting_can_be_retried(client, uploaded_meeting_id, db_session):
    meeting = await db_session.get(Meeting, uploaded_meeting_id)
    assert meeting is not None
    meeting.status, meeting.error = "failed", "Failed at ingest: x"
    await db_session.commit()
    response = await client.post(f"/api/meetings/{uploaded_meeting_id}/retry")
    assert (response.status_code, response.json()["status"]) == (202, "queued")
    assert await db_session.scalar(select(func.count()).select_from(Job)) == 2


async def test_ready_meeting_cannot_be_retried(client, processed_meeting_id):
    response = await client.post(f"/api/meetings/{processed_meeting_id}/retry")
    assert response.status_code == 409


async def test_renaming_creates_a_person_and_reuses_it_ignoring_case(
    client, processed_meeting_id, db_session
):
    speakers = (await client.get(f"/api/meetings/{processed_meeting_id}")).json()["speakers"]
    first = await client.patch(f"/api/speakers/{speakers[0]['id']}", json={"name": " Asha "})
    second = await client.patch(f"/api/speakers/{speakers[1]['id']}", json={"name": "asha"})
    assert (first.json()["name"], second.status_code) == ("Asha", 200)
    assert await db_session.scalar(select(func.count()).select_from(Person)) == 1


async def test_devanagari_names_round_trip(client, processed_meeting_id):
    speaker = (await client.get(f"/api/meetings/{processed_meeting_id}")).json()["speakers"][1]
    renamed = await client.patch(f"/api/speakers/{speaker['id']}", json={"name": "राहुल"})
    assert renamed.json()["name"] == "राहुल"
    detail = (await client.get(f"/api/meetings/{processed_meeting_id}")).json()
    assert detail["action_items"][0]["owner"] == "राहुल"


async def test_blank_name_is_rejected(client, processed_meeting_id):
    speaker = (await client.get(f"/api/meetings/{processed_meeting_id}")).json()["speakers"][0]
    response = await client.patch(f"/api/speakers/{speaker['id']}", json={"name": "  "})
    assert response.status_code == 422


async def test_action_item_can_be_ticked_off(client, processed_meeting_id):
    item = (await client.get(f"/api/meetings/{processed_meeting_id}")).json()["action_items"][0]
    response = await client.patch(f"/api/action-items/{item['id']}", json={"status": "done"})
    assert response.json()["status"] == "done"
    invalid = await client.patch(f"/api/action-items/{item['id']}", json={"status": "finished"})
    assert invalid.status_code == 422


async def test_unknown_speaker_and_action_item_are_404(client):
    assert (await client.patch("/api/speakers/999", json={"name": "Asha"})).status_code == 404
    response = await client.patch("/api/action-items/999", json={"status": "done"})
    assert response.status_code == 404


def test_openapi_export_lists_every_route(tmp_path):
    out = tmp_path / "openapi.json"
    export_openapi([str(out)])
    paths = json.loads(out.read_text(encoding="utf-8"))["paths"]
    assert {
        "/api/health",
        "/api/meetings",
        "/api/meetings/{meeting_id}",
        "/api/meetings/{meeting_id}/audio",
        "/api/meetings/{meeting_id}/retry",
        "/api/speakers/{speaker_id}",
        "/api/action-items/{item_id}",
    } <= set(paths)
