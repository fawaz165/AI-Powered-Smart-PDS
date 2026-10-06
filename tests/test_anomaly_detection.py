import pytest
from backend.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_detect_anomaly_normal_transaction(client):
    """Verifies that an ordinary distribution within entitlement quota is classified as NORMAL/LOW risk."""
    payload = {
        "beneficiary_id": "BEN001",
        "commodity": "Rice",
        "quantity": 20.0,
        "family_size": 4,
        "card_type": "Priority (PHH)",
        "days_since_prior_txn": 28.0,
        "monthly_frequency": 1
    }

    res = client.post("/api/detect-anomaly", json=payload)
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["status"] == "NORMAL"
    assert data["risk_level"] == "LOW"
    assert data["requires_admin_review"] is False


def test_detect_anomaly_suspicious_bulk_excess(client):
    """Verifies that an extreme 95 kg withdrawal against a 20 kg card quota is flagged as SUSPICIOUS."""
    payload = {
        "beneficiary_id": "BEN002",
        "commodity": "Rice",
        "quantity": 95.0,  # Extreme outlier
        "family_size": 4,
        "card_type": "Priority (PHH)",
        "days_since_prior_txn": 1.0,
        "monthly_frequency": 4
    }

    res = client.post("/api/detect-anomaly", json=payload)
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["status"] == "SUSPICIOUS"
    assert data["risk_level"] in ["MEDIUM", "HIGH"]
    assert data["requires_admin_review"] is True
    assert "exceeds" in data["reason"].lower() or "ratio" in data["reason"].lower()
