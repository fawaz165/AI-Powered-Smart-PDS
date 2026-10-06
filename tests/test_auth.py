import pytest
from backend.app import app
from backend.services.auth_service import AuthService


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_auth_success(client):
    """Verifies that admin login succeeds and returns signed token."""
    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert "token" in data["data"]
    assert data["data"]["username"] == "admin"


def test_auth_invalid_credentials(client):
    """Verifies that invalid password returns 401 Unauthorized."""
    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrongpassword_123"
    })
    assert response.status_code == 401
    data = response.get_json()
    assert data["status"] == "error"


def test_auth_me_endpoint_with_token(client):
    """Verifies that /api/auth/me returns profile when valid Bearer token provided."""
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_res.get_json()["data"]["token"]

    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.get_json()["user"]["sub"] == "admin"
