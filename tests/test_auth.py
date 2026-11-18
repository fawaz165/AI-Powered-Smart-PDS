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


def test_unauthorized_user_cannot_register_admin(client):
    """Verifies that an unauthenticated user cannot register an administrator account."""
    res = client.post("/api/auth/register", json={
        "username": "unauthorized_admin",
        "password": "attack_password_123",
        "role": "admin"
    })
    assert res.status_code == 401
    data = res.get_json()
    assert data["status"] == "error"
    assert "Authentication required" in data["message"] or "token" in data["message"]


def test_admin_can_register_new_officer(client):
    """Verifies that an authenticated administrator can register a new district officer."""
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_res.get_json()["data"]["token"]

    reg_res = client.post("/api/auth/register", json={
        "username": "officer_salem_test",
        "password": "officer_pass_123",
        "role": "officer",
        "region": "Salem",
        "email": "salem.officer.test@smartpds.gov.in",
        "full_name": "Salem DSO Test"
    }, headers={"Authorization": f"Bearer {token}"})

    assert reg_res.status_code == 201
    assert reg_res.get_json()["status"] == "success"
