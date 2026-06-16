"""Интеграционные тесты REST-эндпоинтов tasks-svc.

Single-create (POST /v1/tasks) и single-update (PATCH /v1/tasks/{id})
удалены в M2.28 — все мутации через bulk/batch (PRD §7.2, §7.3, §7.6).
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create(client: AsyncClient, title: str = "T", **kwargs: object) -> dict:
    """Создаёт одну задачу через bulk-create и возвращает её полные данные."""
    payload = {"items": [{"title": title, **kwargs}]}
    r = await client.post("/v1/tasks/bulk-create", json=payload)
    assert r.status_code == 200, r.text
    result = r.json()["results"][0]
    assert result["status"] == "ok", result
    g = await client.get(f"/v1/tasks/{result['task_id']}")
    assert g.status_code == 200, g.text
    return g.json()


# === POST /v1/tasks/bulk-create ===


async def test_create_minimal(client: AsyncClient) -> None:
    body = await _create(client, "minimal task")
    assert body["title"] == "minimal task"
    assert body["status"] == "open"
    assert body["labels"] == []
    assert body["blocked_by"] == []


async def test_create_missing_title(client: AsyncClient) -> None:
    """bulk-create с пустым title → validation_failed для этого элемента."""
    r = await client.post("/v1/tasks/bulk-create", json={"items": [{}]})
    assert r.status_code == 422


async def test_create_with_labels_and_status(client: AsyncClient) -> None:
    body = await _create(client, "labeled", labels=["bug", "p1"], status="done")
    assert body["labels"] == ["bug", "p1"]
    assert body["status"] == "done"


async def test_create_duplicate_label(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/tasks/bulk-create",
        json={"items": [{"title": "x", "labels": ["a", "a"]}]},
    )
    # Pydantic-валидация массива срабатывает на уровне айтема → 422.
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


async def test_list_filter_by_id_prefix(client: AsyncClient) -> None:
    """RSQL id== с префиксом <40 символов → LIKE prefix-match."""
    created = await _create(client, "prefix-target")
    full_id = created["id"]
    prefix = full_id[:8]
    r = await client.get("/v1/tasks", params={"filter": f"id=={prefix}"})
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()["items"]}
    assert full_id in ids


# === GET /v1/tasks/{id} ===


async def test_get_existing(client: AsyncClient) -> None:
    created = await _create(client, "found-me")
    r = await client.get(f"/v1/tasks/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


async def test_get_missing(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/" + "0" * 40)
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


async def test_bulk_update_one_by_id_prefix(client: AsyncClient) -> None:
    """bulk-update с фильтром по id-префиксу — заменяет одиночный PATCH."""
    created = await _create(client, "single-target")
    prefix = created["id"][:10]
    r = await client.post(
        "/v1/tasks/bulk-update",
        params={"filter": f"id=={prefix}"},
        json={"patch": {"status": "done"}},
    )
    assert r.status_code == 200
    assert r.json()["succeeded"] == 1
    g = await client.get(f"/v1/tasks/{created['id']}")
    assert g.json()["status"] == "done"


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
    """history генерируется при bulk-update — single PATCH удалён."""
    created = await _create(client, "h")
    await client.post(
        "/v1/tasks/bulk-update",
        params={"filter": f"id=={created['id'][:10]}"},
        json={"patch": {"status": "done"}},
    )
    r = await client.get("/v1/history", params={"task_id": created["id"]})
    assert r.status_code == 200
    body = r.json()
    event_types = {e["event_type"] for e in body["items"]}
    assert "task.created" in event_types
    assert "task.updated" in event_types


async def test_history_missing_task_id(client: AsyncClient) -> None:
    r = await client.get("/v1/history")
    assert r.status_code == 400
