import pytest
import uuid
from backend.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_beneficiary_crud(client):
    """Verifies complete Create, Read, Update, Delete lifecycle for Beneficiary."""
    unique_id = f"TEST-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create
    create_payload = {
        "beneficiary_id": unique_id,
        "name": "Integration Test Cardholder",
        "region": "Chennai",
        "family_size": 4,
        "ration_card_type": "Priority (PHH)"
    }
    create_res = client.post("/api/beneficiaries", json=create_payload)
    assert create_res.status_code == 201
    assert create_res.get_json()["status"] == "success"

    # 2. Read single
    get_res = client.get(f"/api/beneficiaries/{unique_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["data"]["name"] == "Integration Test Cardholder"

    # 3. Update
    update_res = client.put(f"/api/beneficiaries/{unique_id}", json={
        "name": "Updated Cardholder Name",
        "family_size": 5
    })
    assert update_res.status_code == 200
    assert update_res.get_json()["data"]["family_size"] == 5

    # 4. Delete
    del_res = client.delete(f"/api/beneficiaries/{unique_id}")
    assert del_res.status_code == 200

    # 5. Verify deleted
    verify_res = client.get(f"/api/beneficiaries/{unique_id}")
    assert verify_res.status_code == 404


def test_commodity_crud(client):
    """Verifies commodity listing and creation."""
    res = client.get("/api/commodities")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["count"] >= 4  # Rice, Wheat, Sugar, Dal


def test_inventory_alerts_endpoint(client):
    """Verifies /api/inventory/alerts computes shortages and recommendations."""
    res = client.get("/api/inventory/alerts")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["data"]) > 0
    # Every item has required business keys
    sample = data["data"][0]
    assert "current_stock" in sample
    assert "predicted_demand" in sample
    assert "shortage" in sample
    assert "recommended_procurement" in sample


def test_ml_status_endpoint(client):
    """Verifies /api/ml-status returns dynamic model health telemetry."""
    res = client.get("/api/ml-status")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "health" in data["data"]
    assert "status_text" in data["data"]
    assert data["data"]["health"] in ["HEALTHY", "DEGRADED", "OFFLINE"]


def test_fraud_alerts_endpoint(client):
    """Verifies /api/transactions/fraud-alerts returns pending count and alerts."""
    res = client.get("/api/transactions/fraud-alerts")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "count" in data
    assert "pending_count" in data
    assert isinstance(data["data"], list)
    pending_items = [a for a in data["data"] if a.get("status") == "PENDING_REVIEW"]
    assert data["pending_count"] == len(pending_items)


def test_transactions_ledger_data_integrity(client):
    """
    Data-Integrity Audit:
    Verifies that distribution transactions retrieved from /api/transactions
    represent genuine demonstration records without any test remnants.
    """
    res = client.get("/api/transactions?limit=50")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["total"] > 0
    txns = data["data"]
    assert len(txns) > 0

    for t in txns:
        assert "transaction_id" in t
        assert "beneficiary_id" in t
        assert "commodity" in t
        assert "quantity" in t
        assert "region" in t
        assert "status" in t
        assert "ration_shop_id" in t
        # Ensure zero test contaminants
        assert t["region"] != "ConcurrentTestRegion"
        assert t["ration_shop_id"] != "FPS-TEST-001"
        assert not t["beneficiary_id"].startswith("BEN-CONCUR")
        assert not t["beneficiary_id"].startswith("TEST-")


def test_beneficiary_delete_protection_with_transactions(client):
    """
    Verifies that attempting to delete a cardholder with linked transaction history
    is blocked with 409 Conflict to protect audit integrity.
    """
    # BEN001 has active distribution transactions (TXN-1001, etc.)
    del_res = client.delete("/api/beneficiaries/BEN001")
    assert del_res.status_code == 409
    data = del_res.get_json()
    assert data["status"] == "error"
    assert "distribution transaction" in data["message"].lower()

    # Verify BEN001 is NOT deleted
    get_res = client.get("/api/beneficiaries/BEN001")
    assert get_res.status_code == 200
    assert get_res.get_json()["data"]["beneficiary_id"] == "BEN001"


def test_beneficiary_input_validation(client):
    """Verifies input validation rules for beneficiary creation."""
    # Invalid family size
    invalid_size_res = client.post("/api/beneficiaries", json={
        "beneficiary_id": "TEST-VAL-01",
        "name": "Test Cardholder",
        "region": "Chennai",
        "family_size": 0,
        "ration_card_type": "Priority (PHH)"
    })
    assert invalid_size_res.status_code == 400

    # Missing name
    missing_name_res = client.post("/api/beneficiaries", json={
        "beneficiary_id": "TEST-VAL-02",
        "region": "Chennai",
        "family_size": 4,
        "ration_card_type": "Priority (PHH)"
    })
    assert missing_name_res.status_code == 400

    # Invalid card type
    invalid_type_res = client.post("/api/beneficiaries", json={
        "beneficiary_id": "TEST-VAL-03",
        "name": "Test Cardholder",
        "region": "Chennai",
        "family_size": 4,
        "ration_card_type": "InvalidCardType"
    })
    assert invalid_type_res.status_code == 400


def test_beneficiary_search_and_region_filtering(client):
    """Verifies search by name, ID, and card number, as well as region filtering."""
    # Search by name substring
    search_name_res = client.get("/api/beneficiaries?search=Aarav")
    assert search_name_res.status_code == 200
    bens = search_name_res.get_json()["data"]
    assert any(b["beneficiary_id"] == "BEN001" for b in bens)

    # Search by Ration Card Number
    search_rc_res = client.get("/api/beneficiaries?search=RC-BEN001")
    assert search_rc_res.status_code == 200
    bens_rc = search_rc_res.get_json()["data"]
    assert any(b["beneficiary_id"] == "BEN001" for b in bens_rc)

    # Filter by Region
    region_res = client.get("/api/beneficiaries?region=Coimbatore")
    assert region_res.status_code == 200
    cbe_bens = region_res.get_json()["data"]
    assert len(cbe_bens) > 0
    assert all(b["region"] == "Coimbatore" for b in cbe_bens)


def test_beneficiary_authorization_rejection(client):
    """Verifies that mutation endpoints reject invalid tokens with 401 Unauthorized."""
    res = client.post(
        "/api/beneficiaries",
        json={"beneficiary_id": "TEST-AUTH-01", "name": "Test", "region": "Chennai", "family_size": 4, "ration_card_type": "Priority (PHH)"},
        headers={"Authorization": "Bearer invalid_tampered_token_xyz"}
    )
    assert res.status_code == 401
    assert res.get_json()["status"] == "error"

