from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mock_server.app import create_app
from mock_server.core.config import Settings

PREFIX = "/api/v4"
AUTH = {"Authorization": "Bearer local-kommo-token"}
LEAD = 33579273
CONTACT = 37514079


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(tmp_path)), headers=AUTH) as instance:
        yield instance


def test_authentication_and_no_content(client: TestClient) -> None:
    assert client.get("/health", headers={"Authorization": ""}).status_code == 200
    assert client.get(f"{PREFIX}/leads", headers={"Authorization": ""}).status_code == 401
    assert client.get("/_mock/kommo/state", headers={"Authorization": "wrong"}).status_code == 401
    for path in (
        "sources",
        "events",
        "contacts?query=does-not-exist",
        "leads?filter[responsible_user_id][]=9",
    ):
        response = client.get(f"{PREFIX}/{path}")
        assert response.status_code == 204
        assert response.content == b""
    assert client.get(f"{PREFIX}/leads/999").status_code == 404


def test_seed_link_and_payment_fields(client: TestClient) -> None:
    response = client.get(f"{PREFIX}/leads/{LEAD}?with=contacts,source_id")
    assert response.headers["content-type"] == "application/hal+json"
    lead = response.json()
    assert lead["_embedded"]["contacts"] == [{"id": CONTACT, "is_main": True}]
    assert lead["_links"]["self"]["href"].startswith("http://testserver/")
    fields = {f["field_id"]: f["values"][0] for f in lead["custom_fields_values"]}
    assert (
        int(fields[1330363]["value"]) + int(fields[1330365]["value"]) * int(fields[1330367]["value"]) == 2440
    )
    assert fields[1330545]["enum_id"] == 1114013
    assert "contacts" not in client.get(f"{PREFIX}/leads/{LEAD}").json()["_embedded"]


def test_filters_and_pagination(client: TestClient) -> None:
    response = client.post(f"{PREFIX}/leads", json=[{"name": "First"}, {"name": "Second"}])
    assert response.status_code == 200
    url = f"{PREFIX}/leads?limit=1&filter[statuses][0][pipeline_id]=14229720&filter[statuses][0][status_id]=109869808"
    page1 = client.get(url).json()
    assert page1["_embedded"]["leads"][0]["name"] == "First"
    page2 = client.get(page1["_links"]["next"]["href"]).json()
    assert page2["_embedded"]["leads"][0]["name"] == "Second"
    assert "next" not in page2["_links"]
    assert client.get(url + "&page=3").status_code == 204
    assert client.get(url + "&filter[responsible_user_id][]=13716683").status_code == 204
    assert client.get(f"{PREFIX}/leads?filter[created_at][from]=1&order[created_at]=desc").status_code == 200
    assert client.get(f"{PREFIX}/leads?filter[created_at][from]=9999999999").status_code == 204
    assert client.get(f"{PREFIX}/leads?filter[unsupported]=1").status_code == 400


def test_update_fields_and_batch_rollback(client: TestClient) -> None:
    url = f"{PREFIX}/leads/{LEAD}"
    before = client.get(url).json()["custom_fields_values"]
    patch = {"custom_fields_values": [{"field_id": 1330355, "values": [{"value": "new@example.test"}]}]}
    response = client.patch(url, json=patch)
    assert response.status_code == 200
    after = response.json()["custom_fields_values"]
    assert len(after) == len(before)
    assert next(f for f in after if f["field_id"] == 1330355)["field_name"] == "Email"
    count = len(client.get("/_mock/kommo/state").json()["leads"])
    assert client.post(f"{PREFIX}/leads", json=[{"name": "Good"}, {"pipeline_id": 999}]).status_code == 404
    assert len(client.get("/_mock/kommo/state").json()["leads"]) == count
    assert client.patch(url, json={"id": 4}).status_code == 400
    assert client.patch(url, json={"status_id": 999}).status_code == 400
    assert client.patch(url, content="not-json").status_code == 400


def test_create_link_and_duplicate_search(client: TestClient) -> None:
    payload = [
        {
            "name": "Synthetic Contact",
            "custom_fields_values": [
                {"field_code": "PHONE", "values": [{"value": "+12025550124", "enum_code": "WORK"}]}
            ],
        }
    ]
    contact_id = client.post(f"{PREFIX}/contacts", json=payload).json()["_embedded"]["contacts"][0]["id"]
    url = f"{PREFIX}/leads/{LEAD}/link"
    link = [{"to_entity_id": contact_id, "to_entity_type": "contacts"}]
    assert client.post(url, json=link).status_code == 204
    assert client.post(url, json=link).status_code == 204
    result = client.get(f"{PREFIX}/contacts", params={"query": "202-555-0124", "with": "leads"}).json()
    contact = result["_embedded"]["contacts"][0]
    assert contact["_embedded"]["leads"] == [{"id": LEAD}]
    assert contact["custom_fields_values"][0]["field_id"] == 584388
    lead = client.get(f"{PREFIX}/leads/{LEAD}?with=contacts").json()
    assert len(lead["_embedded"]["contacts"]) == 2


def test_notes_both_clients(client: TestClient) -> None:
    for path, extra in [(f"leads/{LEAD}/notes", {}), ("leads/notes", {"entity_id": LEAD})]:
        response = client.post(
            f"{PREFIX}/{path}",
            json=[
                {
                    **extra,
                    "note_type": "common",
                    "params": {"text": "Local test"},
                    "request_id": "correlation-id",
                }
            ],
        )
        assert response.status_code == 200
        assert response.json()["_embedded"]["notes"][0]["id"] > 0
    notes = client.get(f"{PREFIX}/leads/{LEAD}/notes?limit=250").json()["_embedded"]["notes"]
    assert len(notes) == 3
    assert notes[-1]["params"]["text"] == "Local test"


def test_task_lifecycle_and_responsible_filters(client: TestClient) -> None:
    response = client.post(
        f"{PREFIX}/tasks",
        json=[
            {
                "text": "Local payment follow-up",
                "entity_id": LEAD,
                "entity_type": "leads",
                "complete_till": 2000000000,
                "responsible_user_id": 13716683,
            }
        ],
    )
    assert response.status_code == 200
    task_id = response.json()["_embedded"]["tasks"][0]["id"]
    assert (
        client.patch(f"{PREFIX}/tasks/{task_id}", json={"responsible_user_id": 12630411}).status_code == 200
    )
    query = "filter[entity_id][0]=33579273&filter[entity_type][]=leads&filter[is_completed]=0&filter[responsible_user_id][]=12630411"
    tasks = client.get(f"{PREFIX}/tasks?{query}").json()["_embedded"]["tasks"]
    assert [task["id"] for task in tasks] == [task_id]
    assert (
        client.patch(
            f"{PREFIX}/tasks/{task_id}", json={"is_completed": True, "result": {"text": "Done"}}
        ).status_code
        == 200
    )
    assert client.get(f"{PREFIX}/tasks?{query}").status_code == 204


def test_catalogs_users_and_roles(client: TestClient) -> None:
    pipeline = client.get(f"{PREFIX}/leads/pipelines/14229720").json()
    assert pipeline["_embedded"]["statuses"][1]["id"] == 109869808
    status = client.get(f"{PREFIX}/leads/pipelines/14229720/statuses/109869808").json()
    assert status["name"] == "To Assign Leads"
    assert client.get(f"{PREFIX}/leads/pipelines/14229720/statuses/110040496").status_code == 404
    users = client.get(f"{PREFIX}/users?with=role,group").json()["_embedded"]["users"]
    assert all(user["rights"]["is_active"] for user in users)
    assert client.get(f"{PREFIX}/users/10888195").status_code == 200
    roles = client.get(f"{PREFIX}/roles?with=users").json()["_embedded"]["roles"]
    role = roles[0]
    role["rights"]["leads"]["edit"] = "D"
    assert (
        client.patch(f"{PREFIX}/roles/1", json={"name": "Updated", "rights": role["rights"]}).status_code
        == 200
    )
    assert client.get(f"{PREFIX}/roles/1").json()["rights"]["leads"]["edit"] == "D"


def create_unsorted(client: TestClient) -> dict:
    response = client.post(
        f"{PREFIX}/leads/unsorted/forms",
        json=[
            {
                "pipeline_id": 14229720,
                "source_name": "Local Tilda",
                "source_uid": "test-form",
                "request_id": "local",
                "_embedded": {
                    "leads": [{"name": "Incoming test"}],
                    "contacts": [{"name": "Incoming contact"}],
                },
                "metadata": {
                    "form_id": "test-form",
                    "form_name": "Local",
                    "form_page": "http://localhost/",
                    "form_sent_at": 1,
                },
            }
        ],
    )
    assert response.status_code == 200
    return response.json()["_embedded"]["unsorted"][0]


def test_unsorted_create_accept(client: TestClient) -> None:
    incoming = create_unsorted(client)
    uid = incoming["uid"]
    lead_id = incoming["_embedded"]["leads"][0]["id"]
    assert client.get(f"{PREFIX}/leads/unsorted?filter[uid]={uid}").status_code == 200
    assert client.get(f"{PREFIX}/leads/unsorted?filter[pipeline_id]=14229724").status_code == 204
    assert (
        client.post(f"{PREFIX}/leads/unsorted/{uid}/accept", json={"status_id": 109869808}).status_code == 204
    )
    assert client.get(f"{PREFIX}/leads/unsorted?filter[uid]={uid}").status_code == 204
    lead = client.get(f"{PREFIX}/leads/{lead_id}?with=contacts").json()
    assert lead["status_id"] == 109869808
    assert lead["responsible_user_id"] != 0
    assert lead["_embedded"]["contacts"]


def test_chat_link_and_events_via_fixtures(client: TestClient) -> None:
    incoming = create_unsorted(client)
    state = client.get("/_mock/kommo/state").json()
    state["unsorted"][0]["category"] = "chats"
    state["events"] = [
        {
            "id": "local-event",
            "type": "incoming_chat_message",
            "entity_id": CONTACT,
            "entity_type": "contact",
            "created_at": 100,
            "value_after": [{"message": {"id": "local-message"}}],
        }
    ]
    assert client.put("/_mock/kommo/state", json=state).status_code == 200
    events = client.get(
        f"{PREFIX}/events?filter[entity]=contact&filter[entity_id]={CONTACT}&filter[type]=incoming_chat_message,outgoing_chat_message"
    ).json()
    assert events["_embedded"]["events"][0]["value_after"][0]["message"]["id"] == "local-message"
    result = client.post(
        f"{PREFIX}/leads/unsorted/{incoming['uid']}/link",
        json={"link": {"entity_id": LEAD, "entity_type": "leads"}},
    )
    assert result.status_code == 204
    old_lead = incoming["_embedded"]["leads"][0]["id"]
    assert client.get(f"{PREFIX}/leads/{old_lead}").status_code == 204


def test_persistence_reset_and_invalid_import(tmp_path: Path) -> None:
    settings = Settings(tmp_path)
    with TestClient(create_app(settings), headers=AUTH) as first:
        first.patch(f"{PREFIX}/leads/{LEAD}", json={"name": "Persisted"})
    with TestClient(create_app(settings), headers=AUTH) as second:
        assert second.get(f"{PREFIX}/leads/{LEAD}").json()["name"] == "Persisted"
        state = second.get("/_mock/kommo/state").json()
        state["leads"].append(state["leads"][0])
        assert second.put("/_mock/kommo/state", json=state).status_code == 400
        assert second.get(f"{PREFIX}/leads/{LEAD}").json()["name"] == "Persisted"
        assert second.post("/_mock/kommo/reset").status_code == 200
        assert second.get(f"{PREFIX}/leads/{LEAD}").json()["name"] == "Test Client"


def test_task_deadline_tags_and_attachment_fixtures(client: TestClient) -> None:
    created = client.post(
        f"{PREFIX}/leads",
        json=[
            {
                "name": "Lifecycle",
                "_embedded": {"tags": [{"name": "local-test"}]},
            }
        ],
    ).json()["_embedded"]["leads"][0]
    lead_id = created["id"]
    assert created["_embedded"]["tags"][0]["id"] > 0
    task = client.post(
        f"{PREFIX}/tasks",
        json=[
            {
                "entity_id": lead_id,
                "entity_type": "leads",
                "complete_till": 2000000000,
            }
        ],
    ).json()["_embedded"]["tasks"][0]
    assert client.get(f"{PREFIX}/leads/{lead_id}").json()["closest_task_at"] == 2000000000
    client.patch(f"{PREFIX}/tasks/{task['id']}", json={"is_completed": True})
    assert client.get(f"{PREFIX}/leads/{lead_id}").json()["closest_task_at"] is None
    state = client.get("/_mock/kommo/state").json()
    state["notes"].append(
        {
            "id": 999999,
            "entity_id": lead_id,
            "note_type": "attachment",
            "params": {"text": "test.pdf", "file_name": "test.pdf"},
        }
    )
    assert client.put("/_mock/kommo/state", json=state).status_code == 200
    notes = client.get(f"{PREFIX}/leads/{lead_id}/notes").json()["_embedded"]["notes"]
    assert notes[0]["note_type"] == "attachment"
    assert f"/leads/{lead_id}/notes/999999" in notes[0]["_links"]["self"]["href"]
