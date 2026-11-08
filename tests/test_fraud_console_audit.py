import pytest
from datetime import datetime, timedelta
from backend.app import app
from backend.database.mongo import get_db
from backend.services.ml_service import MLService


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_isolation_forest_negative_score_explanation(client):
    """
    Verifies that Isolation Forest anomaly scores are explained as unsupervised tree path distance measures,
    specifically detailing that negative scores (<0) denote shorter tree isolation paths, and are NOT fraud probabilities.
    """
    payload = {
        "beneficiary_id": "BEN001",
        "commodity": "Rice",
        "quantity": 180.0,  # Severe outlier
        "family_size": 4,
        "card_type": "Priority (PHH)",
        "days_since_prior_txn": 0.5,
        "monthly_frequency": 5,
        "hour": 3  # Middle of the night
    }

    res = client.post("/api/detect-anomaly", json=payload)
    assert res.status_code == 200
    data = res.get_json()["data"]

    assert data["status"] == "SUSPICIOUS"
    assert data["anomaly_score"] < 0  # Negative decision score indicates outlier
    assert "score_interpretation" in data
    assert "not a probability" in data["score_interpretation"].lower() or "not a fraud probability" in data["score_interpretation"].lower()
    assert "audit_disclaimer" in data
    assert "not" in data["audit_disclaimer"].lower() and "proof of fraud" in data["audit_disclaimer"].lower()


def test_complete_fraud_review_workflow_verified_legitimate(client):
    """
    Verifies that administrators can review a flagged transaction and submit VERIFIED_LEGITIMATE with comments.
    Verifies that reviewer, decision, timestamp, and comments are stored in the audit trail while original
    transaction quantity and anomaly score are strictly preserved.
    """
    db = get_db()
    txn_id = "TXN-AUDIT-LEGIT-001"

    # Create original transaction
    db.transactions.update_one(
        {"transaction_id": txn_id},
        {"$set": {
            "transaction_id": txn_id,
            "beneficiary_id": "BEN001",
            "commodity": "Rice",
            "quantity": 80.0,
            "region": "Chennai",
            "ration_shop_id": "FPS-CHN-001",
            "anomaly_score": -0.2845,
            "risk_level": "HIGH",
            "status": "SUSPICIOUS",
            "review_status": "PENDING_REVIEW",
            "timestamp": datetime.utcnow() - timedelta(hours=3),
            "audit_trail": [
                {"action": "TRANSACTION_CREATED", "timestamp": (datetime.utcnow() - timedelta(hours=3)).isoformat()}
            ]
        }},
        upsert=True
    )

    # Register in fraud_alerts
    db.fraud_alerts.update_one(
        {"transaction_id": txn_id},
        {"$set": {
            "transaction_id": txn_id,
            "beneficiary_id": "BEN001",
            "commodity": "Rice",
            "quantity": 80.0,
            "region": "Chennai",
            "risk_level": "HIGH",
            "anomaly_score": -0.2845,
            "status": "PENDING_REVIEW",
            "reason": "Quantity (80.0 kg) exceeds Rice monthly entitlement (20.0 kg) by 4.0x",
            "created_at": datetime.utcnow() - timedelta(hours=3),
            "review_history": []
        }},
        upsert=True
    )

    # Perform review: VERIFIED_LEGITIMATE
    review_payload = {
        "officer_id": "OFFICER-AUDIT-01",
        "decision": "VERIFIED_LEGITIMATE",
        "reason": "Authorized advance distribution for family wedding ceremony per civil supplies permit #WD-2026-89.",
        "comments": "Authorized advance distribution for family wedding ceremony per civil supplies permit #WD-2026-89."
    }

    res = client.post(f"/api/transactions/fraud-alerts/{txn_id}/review", json=review_payload)
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["status"] == "success"
    assert res_data["data"]["status"] == "VERIFIED_LEGITIMATE"
    assert res_data["data"]["decision"] == "VERIFIED_LEGITIMATE"
    assert res_data["data"]["officer_id"] == "OFFICER-AUDIT-01"

    # Verify fraud alert record
    alert = db.fraud_alerts.find_one({"transaction_id": txn_id})
    assert alert["status"] == "VERIFIED_LEGITIMATE"
    assert alert["review_decision"] == "VERIFIED_LEGITIMATE"
    assert alert["reviewed_by"] == "OFFICER-AUDIT-01"
    assert "wedding ceremony" in alert["review_reason"]
    assert len(alert["review_history"]) == 1

    # Verify original transaction was preserved without mutating quantity or score
    txn = db.transactions.find_one({"transaction_id": txn_id})
    assert txn["quantity"] == 80.0
    assert txn["anomaly_score"] == -0.2845
    assert txn["review_status"] == "VERIFIED_LEGITIMATE"
    assert any(ev.get("action") == "ADMINISTRATIVE_FRAUD_REVIEW" for ev in txn.get("audit_trail", []))


def test_complete_fraud_review_workflow_confirmed_irregularity(client):
    """
    Verifies that administrators can review a flagged transaction and submit CONFIRMED_IRREGULARITY with comments.
    Verifies that the audit trail preserves the original transaction parameters untouched.
    """
    db = get_db()
    txn_id = "TXN-AUDIT-IRREG-002"

    db.transactions.update_one(
        {"transaction_id": txn_id},
        {"$set": {
            "transaction_id": txn_id,
            "beneficiary_id": "BEN002",
            "commodity": "Sugar",
            "quantity": 25.0,  # 25x sugar cap
            "region": "Madurai",
            "ration_shop_id": "FPS-MDU-001",
            "anomaly_score": -0.3412,
            "risk_level": "HIGH",
            "status": "SUSPICIOUS",
            "review_status": "PENDING_REVIEW",
            "timestamp": datetime.utcnow() - timedelta(hours=5),
            "audit_trail": []
        }},
        upsert=True
    )

    db.fraud_alerts.update_one(
        {"transaction_id": txn_id},
        {"$set": {
            "transaction_id": txn_id,
            "beneficiary_id": "BEN002",
            "commodity": "Sugar",
            "quantity": 25.0,
            "region": "Madurai",
            "risk_level": "HIGH",
            "anomaly_score": -0.3412,
            "status": "PENDING_REVIEW",
            "reason": "Quantity (25.0 kg) exceeds Sugar monthly entitlement (1.0 kg) by 25.0x",
            "created_at": datetime.utcnow() - timedelta(hours=5),
            "review_history": []
        }},
        upsert=True
    )

    # Submit CONFIRMED_IRREGULARITY
    res = client.post(f"/api/transactions/fraud-alerts/{txn_id}/review", json={
        "officer_id": "DIRECTOR-VIGILANCE-09",
        "decision": "CONFIRMED_IRREGULARITY",
        "reason": "Confirmed unauthorized bulk diversion outside shop operating hours without cardholder biometric verification."
    })
    assert res.status_code == 200
    alert = db.fraud_alerts.find_one({"transaction_id": txn_id})
    assert alert["status"] == "CONFIRMED_IRREGULARITY"
    assert alert["review_decision"] == "CONFIRMED_IRREGULARITY"
    assert alert["reviewed_by"] == "DIRECTOR-VIGILANCE-09"

    # Transaction integrity check
    txn = db.transactions.find_one({"transaction_id": txn_id})
    assert txn["quantity"] == 25.0
    assert txn["anomaly_score"] == -0.3412
    assert txn["review_status"] == "CONFIRMED_IRREGULARITY"


def test_fraud_alerts_listing_endpoint_verification_reasons(client):
    """
    Verifies GET /api/transactions/fraud-alerts enriches detection reasons using actual transaction quantities,
    entitlements, and dates, and provides non-wrapping data fields.
    """
    res = client.get("/api/transactions/fraud-alerts")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "data" in data
    assert len(data["data"]) > 0

    for alert in data["data"]:
        assert "transaction_id" in alert
        assert "anomaly_score" in alert
        assert "score_interpretation" in alert
        # Verify explainable detection reason is present and non-empty
        assert "reason" in alert and len(alert["reason"]) > 0
        assert "status" in alert

