"""Test suite for the API health check endpoint."""
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify that GET /api/health returns HTTP 200 and status 'ok'."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_root_endpoint():
    """Verify that GET / returns service info and status 200."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "AquaShift API"
    assert data["health"] == "/api/health"
