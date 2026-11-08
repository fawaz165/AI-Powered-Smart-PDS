import pytest
import json
from datetime import datetime
from backend.app import app
from backend.database.mongo import get_db
from backend.services.inventory_service import InventoryService


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_full_system_integration_lifecycle(client):
    """
    End-to-End System Integration Test:
    1. Authenticate admin user
    2. Register a new test beneficiary
    3. Verify commodity catalog
    4. Predict demand with safety stock
    5. Query inventory and execute grain distribution
    6. Verify thread-safe stock deduction
    7. Trigger duplicate transaction guard (409)
    8. Review flagged transaction with audit persistence
    9. Verify system health and ML status
    """
    db = get_db()

    # 1. User Authentication
    auth_res = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    assert auth_res.status_code == 200, "Admin authentication failed"
    auth_data = auth_res.get_json()["data"]
    token = auth_data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify /api/auth/me
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.get_json()["user"]["role"] == "admin"

    # 2. Beneficiary Management
    ben_id = "BEN-INTEG-001"
    db.beneficiaries.delete_one({"beneficiary_id": ben_id})
    ben_payload = {
        "beneficiary_id": ben_id,
        "name": "Integration Test Household",
        "ration_card_number": "TNPDS-INTEG-9999",
        "ration_card_type": "Priority (PHH)",
        "family_size": 4,
        "region": "Chennai",
        "contact_phone": "9876543210"
    }
    ben_res = client.post("/api/beneficiaries", json=ben_payload, headers=headers)
    assert ben_res.status_code in [200, 201]

    # Verify beneficiary profile in database
    ben_doc = db.beneficiaries.find_one({"beneficiary_id": ben_id})
    assert ben_doc is not None
    assert ben_doc["family_size"] == 4

    # 3. Commodity Catalog
    com_res = client.get("/api/commodities", headers=headers)
    assert com_res.status_code == 200
    com_list = com_res.get_json()["data"]
    assert len(com_list) >= 4
    rice_com = next((c for c in com_list if c["name"].lower() == "rice"), None)
    assert rice_com is not None

    # 4. Demand Prediction with Safety Stock
    pred_res = client.post("/api/predict-demand", json={
        "commodity": "Rice",
        "region": "Chennai",
        "month": 11,
        "year": 2026,
        "beneficiary_count": 12500,
        "current_stock": 3800.0,
        "safety_stock": 500.0,
        "previous_demand": 4200.0,
        "is_custom_scenario": False
    }, headers=headers)
    assert pred_res.status_code == 200
    pred_data = pred_res.get_json()["data"]
    assert pred_data["predicted_demand"] > 0
    assert "confidence_range" in pred_data
    assert pred_data["recommended_procurement"] >= 0

    # 5. Inventory Setup and Query
    # Seed known inventory for Chennai Rice
    db.inventory.update_one(
        {"commodity": "Rice", "region": "Chennai"},
        {"$set": {"current_stock": 5000.0, "safety_stock": 500.0, "last_updated": datetime.utcnow()}},
        upsert=True
    )

    inv_res = client.get("/api/inventory?region=Chennai&commodity=Rice", headers=headers)
    assert inv_res.status_code == 200
    inv_data = inv_res.get_json()["data"]
    chennai_rice = next((i for i in inv_data if i["region"] == "Chennai" and i["commodity"] == "Rice"), None)
    assert chennai_rice is not None
    assert chennai_rice["current_stock"] == 5000.0

    # 6. Execute Valid Grain Distribution Transaction
    txn_res = client.post("/api/transactions", json={
        "beneficiary_id": ben_id,
        "commodity": "Rice",
        "quantity": 15.0,
        "region": "Chennai",
        "ration_shop_id": "FPS-CHN-001"
    }, headers=headers)
    assert txn_res.status_code in [200, 201]
    txn_data = txn_res.get_json()["data"]
    txn_id = txn_data["transaction_id"]

    # Verify inventory was automatically deducted by 15.0 kg
    updated_inv = db.inventory.find_one({"commodity": "Rice", "region": "Chennai"})
    assert updated_inv["current_stock"] == 4985.0

    # 7. Duplicate Submission Guard (Immediate re-submission must fail with 409 Conflict)
    dup_res = client.post("/api/transactions", json={
        "beneficiary_id": ben_id,
        "commodity": "Rice",
        "quantity": 15.0,
        "region": "Chennai",
        "ration_shop_id": "FPS-CHN-001"
    }, headers=headers)
    assert dup_res.status_code == 409
    assert "Duplicate submission" in dup_res.get_json()["message"]

    # 8. Anomaly Flagging and Audit Review Workflow
    # Submit suspicious transaction (100 kg bulk excess)
    # Use different timestamp / shop to avoid duplicate guard
    excess_res = client.post("/api/transactions", json={
        "beneficiary_id": ben_id,
        "commodity": "Wheat",
        "quantity": 85.0,
        "region": "Chennai",
        "ration_shop_id": "FPS-CHN-002"
    }, headers=headers)
    assert excess_res.status_code in [200, 201]
    excess_data = excess_res.get_json()["data"]
    excess_tid = excess_data["transaction_id"]

    # Verify alert was created in fraud_alerts collection
    alert_doc = db.fraud_alerts.find_one({"transaction_id": excess_tid})
    assert alert_doc is not None
    assert alert_doc["status"] == "PENDING_REVIEW"

    # Review alert as admin: Confirm Irregularity
    review_res = client.post(f"/api/transactions/fraud-alerts/{excess_tid}/review", json={
        "decision": "CONFIRMED_IRREGULARITY",
        "reason": "Quantity 85kg significantly exceeds family allocation cap.",
        "officer_id": "admin"
    }, headers=headers)
    assert review_res.status_code == 200
    assert review_res.get_json()["data"]["status"] == "CONFIRMED_IRREGULARITY"

    # Verify persistence of audit history in transactions and fraud_alerts
    persisted_alert = db.fraud_alerts.find_one({"transaction_id": excess_tid})
    assert persisted_alert["review_decision"] == "CONFIRMED_IRREGULARITY"
    assert len(persisted_alert["review_history"]) >= 1

    persisted_txn = db.transactions.find_one({"transaction_id": excess_tid})
    assert persisted_txn["review_status"] == "CONFIRMED_IRREGULARITY"
    assert len(persisted_txn["audit_trail"]) >= 1

    # 9. Health & System Status Endpoints
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    assert health_res.get_json()["status"] == "healthy"

    ml_status_res = client.get("/api/ml-status")
    assert ml_status_res.status_code == 200
    ml_status = ml_status_res.get_json()["data"]
    assert ml_status["demand_model_active"] is True
    assert ml_status["anomaly_model_active"] is True

    # Clean up test beneficiary
    db.beneficiaries.delete_one({"beneficiary_id": ben_id})
    db.transactions.delete_many({"beneficiary_id": ben_id})
    db.fraud_alerts.delete_many({"beneficiary_id": ben_id})
