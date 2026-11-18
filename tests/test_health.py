import pytest
from backend.app import app
from backend.database.mongo import get_db


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_check(client):
    """Verifies GET /api/health returns 200 and healthy status when MongoDB is connected."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "version" in data


def test_health_check_disconnected(client, monkeypatch):
    """Verifies GET /api/health returns 503 and unhealthy status when MongoDB is disconnected."""
    from backend.database.mongo import Database

    class BrokenDB:
        def command(self, cmd):
            raise ConnectionError("Simulated database connection loss")

    broken_instance = type("BrokenDatabase", (), {"db": BrokenDB()})()
    monkeypatch.setattr(Database, "__new__", lambda cls: broken_instance)

    response = client.get("/api/health")
    assert response.status_code == 503
    data = response.get_json()
    assert data["status"] == "unhealthy"
    assert data["database"] == "disconnected"
    assert "version" in data


def test_database_connection():
    """Verifies MongoDB database ping response."""
    db = get_db()
    res = db.command("ping")
    assert res.get("ok") == 1.0
