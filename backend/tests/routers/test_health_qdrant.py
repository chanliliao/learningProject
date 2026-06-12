from fastapi.testclient import TestClient
from app.main import app
from app.routers import health as health_router

client = TestClient(app)


def test_health_qdrant_ok(monkeypatch):
    async def mock_ping_ok():
        pass

    monkeypatch.setattr(health_router, "ping_qdrant", mock_ping_ok)
    response = client.get("/api/health/qdrant")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_qdrant_error(monkeypatch):
    async def mock_ping_fail():
        raise Exception("qdrant down")

    monkeypatch.setattr(health_router, "ping_qdrant", mock_ping_fail)
    response = client.get("/api/health/qdrant")
    assert response.status_code == 503
