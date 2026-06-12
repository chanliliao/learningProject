import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import db as db_module


client = TestClient(app)


def test_health_db_ok(monkeypatch):
    async def mock_ping_ok():
        pass

    monkeypatch.setattr(db_module, "ping_db", mock_ping_ok)
    response = client.get("/api/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_error(monkeypatch):
    async def mock_ping_fail():
        raise Exception("db down")

    monkeypatch.setattr(db_module, "ping_db", mock_ping_fail)
    response = client.get("/api/health/db")
    assert response.status_code == 503
