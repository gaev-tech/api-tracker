from fastapi.testclient import TestClient

from tasks_service.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_ping_returns_pong() -> None:
    response = client.get("/v1/ping")
    assert response.status_code == 200
    assert response.json() == {"message": "pong"}


def test_openapi_json_available() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "api-tracker tasks-service"
    assert "/healthz" in spec["paths"]
