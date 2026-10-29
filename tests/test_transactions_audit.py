import threading
import pytest
from datetime import datetime
from backend.app import create_app
from backend.database.mongo import get_db
from backend.services.inventory_service import InventoryService


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def setup_teardown_audit_data():
    """Sets up an isolated beneficiary and inventory stock for transaction audit tests, cleaning up after."""
    db = get_db()
    # Create test beneficiary
    db.beneficiaries.delete_many({"beneficiary_id": "BEN-TEST-AUDIT"})
    db.beneficiaries.insert_one({
        "beneficiary_id": "BEN-TEST-AUDIT",
        "name": "Audit Test Beneficiary",
        "region": "TestAuditRegion",
        "family_size": 4,
        "ration_card_type": "Priority (PHH)",
        "ration_card_number": "RC-TEST-AUDIT-001",
        "monthly_quota": {
            "Rice": 20.0,
            "Wheat": 8.0,
            "Sugar": 2.0,
            "Dal": 1.0
        }
    })

    # Create test inventory
    db.inventory.delete_many({"region": "TestAuditRegion"})
    db.inventory.insert_one({
        "commodity": "Rice",
        "commodity_code": "COM-RIC",
        "region": "TestAuditRegion",
        "current_stock": 100.0,
        "buffer_stock": 20.0,
        "last_updated": datetime.utcnow()
    })

    yield

    # Teardown
    db.beneficiaries.delete_many({"beneficiary_id": "BEN-TEST-AUDIT"})
    db.inventory.delete_many({"region": "TestAuditRegion"})
    db.transactions.delete_many({"region": "TestAuditRegion"})
    db.fraud_alerts.delete_many({"region": "TestAuditRegion"})


def test_normal_distribution(client):
    """Test 1: Normal distribution deducts inventory, records transaction, and generates audit trail."""
    payload = {
        "beneficiary_id": "BEN-TEST-AUDIT",
        "commodity": "Rice",
        "quantity": 10.0,
        "region": "TestAuditRegion",
        "ration_shop_id": "FPS-AUDIT-001"
    }

    res = client.post("/api/transactions", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "success"
    assert "data" in data
    txn_data = data["data"]
    assert txn_data["success"] is True
    assert txn_data["quantity_distributed"] == 10.0
    assert txn_data["remaining_stock"] == 90.0

    # Verify database persistence
    db = get_db()
    txn = db.transactions.find_one({"transaction_id": txn_data["transaction_id"]})
    assert txn is not None
    assert txn["beneficiary_id"] == "BEN-TEST-AUDIT"
    assert txn["processing_status"] == "COMPLETED"
    assert txn["previous_stock"] == 100.0
    assert txn["remaining_stock"] == 90.0
    assert isinstance(txn["audit_trail"], list)
    assert len(txn["audit_trail"]) >= 4

    # Verify inventory was updated
    inv = db.inventory.find_one({"region": "TestAuditRegion", "commodity": "Rice"})
    assert inv["current_stock"] == 90.0


def test_invalid_beneficiary_rejected(client):
    """Test 2: Unknown beneficiary ID returns 404 with clear validation error message."""
    payload = {
        "beneficiary_id": "BEN-DOES-NOT-EXIST-999",
        "commodity": "Rice",
        "quantity": 5.0,
        "region": "TestAuditRegion",
        "ration_shop_id": "FPS-AUDIT-001"
    }

    res = client.post("/api/transactions", json=payload)
    assert res.status_code == 404
    data = res.get_json()
    assert data["status"] == "error"
    assert "not found in the registry" in data["message"]

    # Verify stock was untouched
    db = get_db()
    inv = db.inventory.find_one({"region": "TestAuditRegion", "commodity": "Rice"})
    assert inv["current_stock"] == 100.0


def test_insufficient_stock_rejected(client):
    """Test 3: Attempting to withdraw more than available inventory is rejected with 400."""
    payload = {
        "beneficiary_id": "BEN-TEST-AUDIT",
        "commodity": "Rice",
        "quantity": 150.0,  # Available is only 100.0
        "region": "TestAuditRegion",
        "ration_shop_id": "FPS-AUDIT-001"
    }

    res = client.post("/api/transactions", json=payload)
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert "Insufficient stock" in data["message"]

    # Verify stock remained 100.0
    db = get_db()
    inv = db.inventory.find_one({"region": "TestAuditRegion", "commodity": "Rice"})
    assert inv["current_stock"] == 100.0


def test_duplicate_submission_prevented(client):
    """Test 4: Immediate duplicate transaction within 60s is blocked with 409 Conflict."""
    payload = {
        "beneficiary_id": "BEN-TEST-AUDIT",
        "commodity": "Rice",
        "quantity": 5.0,
        "region": "TestAuditRegion",
        "ration_shop_id": "FPS-AUDIT-001"
    }

    # First request succeeds
    res1 = client.post("/api/transactions", json=payload)
    assert res1.status_code == 201

    # Second immediate request fails with 409
    res2 = client.post("/api/transactions", json=payload)
    assert res2.status_code == 409
    data = res2.get_json()
    assert data["status"] == "error"
    assert "Duplicate submission detected" in data["message"]


def test_excessive_quantity_anomaly_scoring(client):
    """Test 5: Excessive quantity triggers ML anomaly scoring and warning."""
    db = get_db()
    # Set high stock so stock check passes
    db.inventory.update_one({"region": "TestAuditRegion", "commodity": "Rice"}, {"$set": {"current_stock": 500.0}})

    payload = {
        "beneficiary_id": "BEN-TEST-AUDIT",
        "commodity": "Rice",
        "quantity": 90.0,  # Monthly entitlement is 20.0 kg -> 4.5x quota!
        "region": "TestAuditRegion",
        "ration_shop_id": "FPS-AUDIT-001"
    }

    res = client.post("/api/transactions", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "success"
    assert "entitlement_warning" in data
    assert "exceeds monthly entitlement" in data["entitlement_warning"]

    # ML Pipeline anomaly check
    anomaly = data["anomaly_analysis"]
    assert anomaly["status"] == "SUSPICIOUS"
    assert anomaly["risk_level"] in ["HIGH", "MEDIUM"]
    assert isinstance(anomaly["anomaly_score"], float)
    assert anomaly["requires_admin_review"] is True


def test_concurrent_transactions_safety():
    """Test 6: Concurrent threads distributing stock do not corrupt inventory or cause race condition."""
    commodity = "Rice"
    region = "TestAuditRegion"

    # Start with 100 kg
    InventoryService.update_stock(commodity, region, 100.0)

    # 4 concurrent threads each distributing 20 kg -> Total 80 kg, final should be 20 kg
    results = []

    def distribute_worker(thread_num):
        res = InventoryService.process_transaction_distribution(
            commodity=commodity,
            region=region,
            quantity=20.0,
            beneficiary_id=f"BEN-CONCUR-{thread_num}",
            ration_shop_id="FPS-AUDIT-001"
        )
        results.append(res)

    threads = [threading.Thread(target=distribute_worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All 4 transactions succeeded
    assert len(results) == 4
    for r in results:
        assert r["success"] is True

    # Final stock must be exactly 20.0 kg (100 - 4 * 20 = 20)
    stock_doc = InventoryService.get_stock(commodity, region)
    assert stock_doc["current_stock"] == 20.0
