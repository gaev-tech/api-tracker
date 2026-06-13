"""Интеграционные тесты REST-эндпоинтов tasks-svc (M1)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create(client: AsyncClient, title: str = "T", **kwargs: object) -> dict:
    payload = {"title": title, **kwargs}
    r = await client.post("/v1/tasks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# === POST /v1/tasks ===


async def test_create_minimal(client: AsyncClient) -> None:
    body = await _create(client, "minimal task")
    assert body["title"] == "minimal task"
    assert body["status"] == "open"
    assert body["labels"] == []
    assert body["blocked_by"] == []


async def test_create_missing_title(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={})
    assert r.status_code == 422


async def test_create_with_labels_and_status(client: AsyncClient) -> None:
    body = await _create(client, "labeled", labels=["bug", "p1"], status="done")
    assert body["labels"] == ["bug", "p1"]
    assert body["status"] == "done"


async def test_create_duplicate_label(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "labels": ["a", "a"]})
    assert r.status_code == 422


# === GET /v1/tasks ===


async def test_list_empty(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


async def test_list_with_filter(client: AsyncClient) -> None:
    await _create(client, "a", status="open")
    await _create(client, "b", status="done")
    r = await client.get("/v1/tasks", params={"filter": "status==done"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "b"


async def test_list_invalid_rsql(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks", params={"filter": "status~~open"})
    assert r.status_code == 400


async def test_list_unknown_field(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks", params={"filter": "nope==1"})
    assert r.status_code == 400


async def test_list_limit_too_large(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks", params={"limit": 201})
    assert r.status_code == 422


# === GET /v1/tasks/{id} ===


async def test_get_existing(client: AsyncClient) -> None:
    created = await _create(client, "found-me")
    r = await client.get(f"/v1/tasks/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


async def test_get_missing(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# === PATCH /v1/tasks/{id} ===


async def test_patch_title_and_status(client: AsyncClient) -> None:
    created = await _create(client, "old")
    r = await client.patch(
        f"/v1/tasks/{created['id']}", json={"title": "new", "status": "done"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "new" and body["status"] == "done"


async def test_patch_missing(client: AsyncClient) -> None:
    r = await client.patch(
        "/v1/tasks/00000000-0000-0000-0000-000000000000", json={"title": "x"}
    )
    assert r.status_code == 404


# === POST /v1/tasks/bulk-update ===


async def test_bulk_update_partial(client: AsyncClient) -> None:
    await _create(client, "a", labels=["x"])
    await _create(client, "b", labels=["x"])
    await _create(client, "c", labels=["y"])
    r = await client.post(
        "/v1/tasks/bulk-update",
        params={"filter": "labels=in=(x)"},
        json={"patch": {"status": "done"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and body["succeeded"] == 2


async def test_bulk_update_invalid_filter(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/tasks/bulk-update",
        params={"filter": "bad"},
        json={"patch": {"status": "done"}},
    )
    assert r.status_code == 400


# === POST /v1/tasks/batch-update ===


async def test_batch_update_atomic(client: AsyncClient) -> None:
    await _create(client, "x", labels=["x"])
    await _create(client, "y", labels=["x"])
    r = await client.post(
        "/v1/tasks/batch-update",
        params={"filter": "labels=in=(x)"},
        json={"patch": {"status": "done"}},
    )
    assert r.status_code == 200
    assert r.json()["affected"] == 2


async def test_batch_update_invalid(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/tasks/batch-update",
        params={"filter": "bad"},
        json={"patch": {"status": "done"}},
    )
    assert r.status_code == 400


# === POST /v1/tasks/bulk-create ===


async def test_bulk_create_mixed(client: AsyncClient) -> None:
    payload = {
        "items": [
            {"title": "ok1"},
            {"title": "ok2", "labels": ["x"]},
        ]
    }
    r = await client.post("/v1/tasks/bulk-create", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert all(it["status"] == "ok" for it in body["results"])


async def test_bulk_create_invalid_root(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks/bulk-create", json={"items": "not-a-list"})
    assert r.status_code == 422


# === POST /v1/tasks/batch-create ===


async def test_batch_create_happy(client: AsyncClient) -> None:
    payload = {"items": [{"title": "x"}, {"title": "y"}]}
    r = await client.post("/v1/tasks/batch-create", json=payload)
    assert r.status_code == 201
    assert len(r.json()["task_ids"]) == 2


async def test_batch_create_invalid(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks/batch-create", json={"items": [{"title": ""}]})
    assert r.status_code == 422


# === GET /v1/history ===


async def test_history_task(client: AsyncClient) -> None:
    created = await _create(client, "h")
    await client.patch(f"/v1/tasks/{created['id']}", json={"status": "done"})
    r = await client.get("/v1/history", params={"task_id": created["id"]})
    assert r.status_code == 200
    body = r.json()
    event_types = {e["event_type"] for e in body["items"]}
    assert "task.created" in event_types
    assert "task.updated" in event_types


async def test_history_missing_task_id(client: AsyncClient) -> None:
    r = await client.get("/v1/history")
    assert r.status_code == 400
