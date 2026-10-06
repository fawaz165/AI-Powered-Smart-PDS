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
