import pytest
from backend.app import app
from backend.database.mongo import get_db


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_check(client):
    """Verifies GET /api/health returns 200 and healthy status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_database_connection():
    """Verifies MongoDB database ping response."""
    db = get_db()
    res = db.command("ping")
    assert res.get("ok") == 1.0
