from fastapi.testclient import TestClient
from app.main import app
from app.routers import health as health_router

client = TestClient(app)


def test_health_llm_ok(monkeypatch):
    async def mock_ping_ok(mode=None):
        return "Hello there"

    monkeypatch.setattr(health_router, "ping_llm", mock_ping_ok)
    response = client.get("/api/health/llm")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert len(data["reply"]) > 0


def test_health_llm_error(monkeypatch):
    async def mock_ping_fail(mode=None):
        raise Exception("llm down")

    monkeypatch.setattr(health_router, "ping_llm", mock_ping_fail)
    response = client.get("/api/health/llm")
    assert response.status_code == 503
