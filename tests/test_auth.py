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


def test_first_user_registration_requires_bootstrap_key(client, monkeypatch):
    """Verifies that when database has 0 users, unauthenticated registration is rejected without bootstrap key."""
    from backend.database.mongo import get_db
    real_db = get_db()

    class FakeDB:
        def __getattr__(self, name):
            if name == "users":
                class FakeUsers:
                    def count_documents(self, *args, **kwargs):
                        return 0
                    def find_one(self, *args, **kwargs):
                        return None
                    def insert_one(self, *args, **kwargs):
                        return real_db.users.insert_one(*args, **kwargs)
                return FakeUsers()
            return getattr(real_db, name)

    monkeypatch.setattr("backend.routes.auth_routes.get_db", lambda: FakeDB())

    res = client.post("/api/auth/register", json={
        "username": "first_admin_hacker",
        "password": "some_password_123",
        "role": "admin"
    })
    assert res.status_code == 401
    assert "BOOTSTRAP_ADMIN_KEY" in res.get_json()["message"]


def test_first_user_registration_succeeds_with_bootstrap_key(client, monkeypatch):
    """Verifies that when database has 0 users, registration succeeds with matching BOOTSTRAP_ADMIN_KEY."""
    from backend.database.mongo import get_db
    real_db = get_db()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_KEY", "secure_secret_setup_key_2026")

    class FakeDB:
        def __getattr__(self, name):
            if name == "users":
                class FakeUsers:
                    def count_documents(self, *args, **kwargs):
                        return 0
                    def find_one(self, *args, **kwargs):
                        return None
                    def insert_one(self, *args, **kwargs):
                        return real_db.users.insert_one(*args, **kwargs)
                return FakeUsers()
            return getattr(real_db, name)

    monkeypatch.setattr("backend.routes.auth_routes.get_db", lambda: FakeDB())

    res = client.post("/api/auth/register", json={
        "username": "bootstrap_admin_test",
        "password": "admin_secure_123",
        "role": "admin"
    }, headers={"X-Bootstrap-Key": "secure_secret_setup_key_2026"})
    assert res.status_code == 201
    assert res.get_json()["status"] == "success"


def test_first_user_registration_invalid_bootstrap_key(client, monkeypatch):
    """Verifies that registration is rejected with 401 when an invalid bootstrap key is supplied."""
    from backend.database.mongo import get_db
    real_db = get_db()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_KEY", "correct_secure_bootstrap_key")

    class FakeDB:
        def __getattr__(self, name):
            if name == "users":
                class FakeUsers:
                    def count_documents(self, *args, **kwargs):
                        return 0
                    def find_one(self, *args, **kwargs):
                        return None
                    def insert_one(self, *args, **kwargs):
                        return real_db.users.insert_one(*args, **kwargs)
                return FakeUsers()
            return getattr(real_db, name)

    monkeypatch.setattr("backend.routes.auth_routes.get_db", lambda: FakeDB())

    res = client.post("/api/auth/register", json={
        "username": "attacker_admin",
        "password": "some_password_123",
        "role": "admin"
    }, headers={"X-Bootstrap-Key": "wrong_invalid_bootstrap_key"})
    assert res.status_code == 401
    assert "Authentication required" in res.get_json()["message"]


def test_first_user_registration_non_admin_officer_rejected(client, monkeypatch):
    """Verifies that when database has 0 users, non-admin (officer) registration is forbidden with 403."""
    from backend.database.mongo import get_db
    real_db = get_db()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_KEY", "secure_secret_setup_key_2026")

    class FakeDB:
        def __getattr__(self, name):
            if name == "users":
                class FakeUsers:
                    def count_documents(self, *args, **kwargs):
                        return 0
                    def find_one(self, *args, **kwargs):
                        return None
                    def insert_one(self, *args, **kwargs):
                        return real_db.users.insert_one(*args, **kwargs)
                return FakeUsers()
            return getattr(real_db, name)

    monkeypatch.setattr("backend.routes.auth_routes.get_db", lambda: FakeDB())

    res = client.post("/api/auth/register", json={
        "username": "first_officer_user",
        "password": "officer_pass_123",
        "role": "officer"
    }, headers={"X-Bootstrap-Key": "secure_secret_setup_key_2026"})
    assert res.status_code == 403
    assert "administrator" in res.get_json()["message"]


def test_first_user_registration_non_admin_dealer_rejected(client, monkeypatch):
    """Verifies that when database has 0 users, non-admin (dealer) registration is forbidden with 403."""
    from backend.database.mongo import get_db
    real_db = get_db()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_KEY", "secure_secret_setup_key_2026")

    class FakeDB:
        def __getattr__(self, name):
            if name == "users":
                class FakeUsers:
                    def count_documents(self, *args, **kwargs):
                        return 0
                    def find_one(self, *args, **kwargs):
                        return None
                    def insert_one(self, *args, **kwargs):
                        return real_db.users.insert_one(*args, **kwargs)
                return FakeUsers()
            return getattr(real_db, name)

    monkeypatch.setattr("backend.routes.auth_routes.get_db", lambda: FakeDB())

    res = client.post("/api/auth/register", json={
        "username": "first_dealer_user",
        "password": "dealer_pass_123",
        "role": "dealer"
    }, headers={"X-Bootstrap-Key": "secure_secret_setup_key_2026"})
    assert res.status_code == 403
    assert "administrator" in res.get_json()["message"]
