from fastapi.testclient import TestClient

from auth_service.main import create_app

app = create_app(with_lifespan=False)
client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_openapi_json_available() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "api-tracker auth-service"
