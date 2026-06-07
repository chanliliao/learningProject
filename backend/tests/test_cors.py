from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_cors_header_for_frontend_origin():
    response = client.get("/health", headers={"Origin": "http://localhost:5174"})
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
