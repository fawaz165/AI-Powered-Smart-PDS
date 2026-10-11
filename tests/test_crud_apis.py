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


def test_commodity_catalog_retrieval_and_rate_distinction(client):
    """
    Verifies that commodity records are retrieved from the database,
    enriched with operational linkages, and that verified official NFSA rates
    are clearly distinguished from synthetic demonstration welfare values.
    """
    res = client.get("/api/commodities")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["count"] >= 4

    comms = {c["commodity_code"]: c for c in data["data"]}
    assert "COM-RIC" in comms
    assert "COM-WHT" in comms
    assert "COM-SUG" in comms
    assert "COM-DAL" in comms

    # Official statutory NFSA rates
    rice = comms["COM-RIC"]
    assert rice["rate_type"] == "OFFICIAL_NFSA"
    assert rice["is_verified"] is True
    assert rice["is_demonstration"] is False
    assert rice["subsidized_price"] == 0.0
    assert rice["market_price"] == 42.0
    assert rice["subsidy_amount"] == 42.0
    assert rice["subsidy_percentage"] == 100.0
    assert rice["linked_inventory_count"] >= 5
    assert rice["linked_transactions_count"] > 0

    wheat = comms["COM-WHT"]
    assert wheat["rate_type"] == "OFFICIAL_NFSA"
    assert wheat["is_verified"] is True
    assert wheat["is_demonstration"] is False
    assert wheat["subsidized_price"] == 2.0
    assert wheat["market_price"] == 34.0
    assert wheat["subsidy_amount"] == 32.0
    assert wheat["subsidy_percentage"] == 94.12

    sugar = comms["COM-SUG"]
    assert sugar["rate_type"] == "OFFICIAL_NFSA"
    assert sugar["is_verified"] is True
    assert sugar["is_demonstration"] is False
    assert sugar["subsidized_price"] == 13.5
    assert sugar["market_price"] == 45.0
    assert sugar["subsidy_amount"] == 31.5
    assert sugar["subsidy_percentage"] == 70.0

    # Synthetic demonstration rate (never labeled official)
    dal = comms["COM-DAL"]
    assert dal["rate_type"] == "DEMONSTRATION"
    assert dal["is_verified"] is False
    assert dal["is_demonstration"] is True
    assert dal["subsidized_price"] == 30.0
    assert dal["market_price"] == 130.0
    assert dal["subsidy_amount"] == 100.0
    assert dal["subsidy_percentage"] == 76.92

    # Verify summary statistics and clearly defined averaging method
    assert "summary" in data
    summary = data["summary"]
    assert summary["total_count"] == 4
    assert summary["official_count"] == 3
    assert summary["demo_count"] == 1
    assert summary["benchmarked_count"] == 4
    assert summary["average_subsidy_discount"] == 85.3
    assert summary["averaging_method"] == "arithmetic_mean_of_valid_benchmark_discounts"


def test_commodity_validation_and_duplicate_prevention(client):
    """
    Verifies payload validation, subsidy calculations, and duplicate prevention:
    - Code format and length validation
    - Name length and regex validation
    - Non-negative subsidized and market prices
    - Market price cannot be less than subsidized price
    - Unverified price (> 15.0) cannot be labeled as OFFICIAL_NFSA
    - 409 Conflict rejection for duplicate code or duplicate name
    """
    # 1. Negative subsidized price
    res_neg_sub = client.post("/api/commodities", json={
        "commodity_code": "COM-VAL1",
        "name": "Validation Test Grain",
        "subsidized_price": -5.0
    })
    assert res_neg_sub.status_code == 400
    assert "subsidized_price" in str(res_neg_sub.get_json()).lower()

    # 2. Negative market price
    res_neg_mkt = client.post("/api/commodities", json={
        "commodity_code": "COM-VAL2",
        "name": "Validation Test Grain 2",
        "subsidized_price": 10.0,
        "market_price": -20.0
    })
    assert res_neg_mkt.status_code == 400
    assert "market_price" in str(res_neg_mkt.get_json()).lower()

    # 3. Market price lower than subsidized price
    res_mkt_low = client.post("/api/commodities", json={
        "commodity_code": "COM-VAL3",
        "name": "Validation Low Benchmark",
        "subsidized_price": 50.0,
        "market_price": 30.0
    })
    assert res_mkt_low.status_code == 400
    assert "market_price cannot be less than subsidized_price" in str(res_mkt_low.get_json()).lower()

    # 4. Unverified price cannot be labeled as OFFICIAL_NFSA
    res_unverified_nfsa = client.post("/api/commodities", json={
        "commodity_code": "COM-VAL4",
        "name": "Unverified Expensive Grain",
        "subsidized_price": 40.0,
        "market_price": 80.0,
        "rate_type": "OFFICIAL_NFSA"
    })
    assert res_unverified_nfsa.status_code == 400
    assert "unverified price cannot be labeled as official_nfsa" in str(res_unverified_nfsa.get_json()).lower()

    # 5. Invalid commodity code pattern
    res_bad_code = client.post("/api/commodities", json={
        "commodity_code": "AB",
        "name": "Validation Test Grain Bad Code"
    })
    assert res_bad_code.status_code == 400

    # 6. Short name or invalid name pattern
    res_short_name = client.post("/api/commodities", json={
        "commodity_code": "COM-VAL-SHORT",
        "name": "X"
    })
    assert res_short_name.status_code == 400

    res_bad_name = client.post("/api/commodities", json={
        "commodity_code": "COM-VAL-BADNAME",
        "name": "123##Invalid"
    })
    assert res_bad_name.status_code == 400

    # 7. Invalid measurement unit (empty or too long)
    res_empty_unit = client.post("/api/commodities", json={
        "commodity_code": "COM-VAL-UNIT",
        "name": "Validation Unit Grain",
        "unit": ""
    })
    assert res_empty_unit.status_code == 400

    res_long_unit = client.post("/api/commodities", json={
        "commodity_code": "COM-VAL-UNIT2",
        "name": "Validation Unit Grain 2",
        "unit": "excessively_long_unit_name"
    })
    assert res_long_unit.status_code == 400

    # 8. Duplicate code rejection (COM-RIC already exists)
    res_dup_code = client.post("/api/commodities", json={
        "commodity_code": "COM-RIC",
        "name": "Duplicate Code Grain",
        "subsidized_price": 5.0
    })
    assert res_dup_code.status_code == 409
    assert "already exists" in res_dup_code.get_json()["message"]

    # 9. Duplicate name rejection ('Rice' already exists)
    res_dup_name = client.post("/api/commodities", json={
        "commodity_code": "COM-NEW-RIC",
        "name": "Rice",
        "subsidized_price": 5.0
    })
    assert res_dup_name.status_code == 409
    assert "already exists" in res_dup_name.get_json()["message"]


def test_commodity_crud_lifecycle_and_configurable_pricing(client):
    """
    Verifies full lifecycle of Add Commodity:
    - Creation and persistent storage in database
    - Configurable subsidized pricing and market benchmark update (PUT)
    - Rejection of invalid price updates and invalid benchmark relationships
    - Operational deletion protection when linked, and clean deletion when unlinked
    - Guaranteed cleanup in finally block for complete test isolation
    """
    from backend.database.mongo import get_db
    test_code = f"COM-MIL-{uuid.uuid4().hex[:6].upper()}"
    test_name = f"Millet-{uuid.uuid4().hex[:4].upper()}"
    db = get_db()

    try:
        # 1. Create new commodity with valid official coarse grain pricing (<= ₹13.50)
        create_payload = {
            "commodity_code": test_code,
            "name": test_name,
            "unit": "kg",
            "subsidized_price": 1.5,
            "market_price": 35.0,
            "rate_type": "OFFICIAL_NFSA",
            "description": "Nutritious coarse grain millet"
        }
        create_res = client.post("/api/commodities", json=create_payload)
        assert create_res.status_code == 201
        created_data = create_res.get_json()["data"]
        assert created_data["commodity_code"] == test_code
        assert created_data["subsidized_price"] == 1.5
        assert created_data["market_price"] == 35.0
        assert created_data["subsidy_amount"] == 33.5
        assert created_data["is_verified"] is True
        assert created_data["is_demonstration"] is False

        # 2. Verify database persistence in MongoDB
        db_doc = db.commodities.find_one({"commodity_code": test_code}, {"_id": 0})
        assert db_doc is not None
        assert db_doc["name"] == test_name
        assert db_doc["subsidized_price"] == 1.5
        assert db_doc["market_price"] == 35.0

        # 3. Read single commodity via API
        get_res = client.get(f"/api/commodities/{test_code}")
        assert get_res.status_code == 200
        assert get_res.get_json()["data"]["name"] == test_name

        # 4. Make subsidized price and classification configurable via PUT
        update_res = client.put(f"/api/commodities/{test_code}", json={
            "subsidized_price": 2.25,
            "market_price": 38.0,
            "rate_type": "STATE_SUBSIDY",
            "description": "Updated state subsidy policy rate"
        })
        assert update_res.status_code == 200
        updated_data = update_res.get_json()["data"]
        assert updated_data["subsidized_price"] == 2.25
        assert updated_data["market_price"] == 38.0
        assert updated_data["rate_type"] == "STATE_SUBSIDY"
        assert updated_data["subsidy_amount"] == 35.75
        assert updated_data["is_demonstration"] is False

        # 5. Reject negative price update
        bad_update = client.put(f"/api/commodities/{test_code}", json={"subsidized_price": -10.0})
        assert bad_update.status_code == 400

        # 6. Reject market price less than subsidized price on PUT
        bad_benchmark = client.put(f"/api/commodities/{test_code}", json={"subsidized_price": 30.0, "market_price": 20.0})
        assert bad_benchmark.status_code == 400

        # 7. Reject labeling unverified rate (> 15.0) as OFFICIAL_NFSA on PUT
        bad_official = client.put(f"/api/commodities/{test_code}", json={"subsidized_price": 25.0, "rate_type": "OFFICIAL_NFSA"})
        assert bad_official.status_code == 400

        # 8. Verify operational deletion restriction for linked commodity (COM-RIC)
        rice_del_res = client.delete("/api/commodities/COM-RIC")
        assert rice_del_res.status_code == 409
        assert "operational integrity" in rice_del_res.get_json()["message"].lower()

        # 9. Cleanly delete unlinked test commodity
        del_res = client.delete(f"/api/commodities/{test_code}")
        assert del_res.status_code == 200

        # 10. Verify deleted from DB
        assert db.commodities.find_one({"commodity_code": test_code}) is None

    finally:
        # Guarantee test isolation: always purge test record from MongoDB
        db.commodities.delete_many({"commodity_code": test_code})


def test_commodity_ids_linked_with_inventory_and_forecasting(client):
    """
    Verifies that commodity IDs / codes are consistently linked with:
    1. Demand forecasting (/api/predict-demand)
    2. Regional inventory alerts (/api/inventory/alerts)
    """
    # 1. Forecasting with commodity_code COM-RIC
    pred_res_code = client.post("/api/predict-demand", json={
        "commodity_code": "COM-RIC",
        "region": "Chennai",
        "month": 1,
        "current_stock": 3800.0,
        "previous_demand": 4200.0
    })
    assert pred_res_code.status_code == 200
    pred_data = pred_res_code.get_json()["data"]
    assert pred_data["commodity"] == "Rice"
    assert pred_data["commodity_code"] == "COM-RIC"
    assert "predicted_demand" in pred_data
    assert "shortage" in pred_data

    # 2. Forecasting with commodity name 'Wheat' resolves COM-WHT
    pred_res_name = client.post("/api/predict-demand", json={
        "commodity": "Wheat",
        "region": "Chennai",
        "month": 2,
        "current_stock": 2500.0,
        "previous_demand": 2600.0
    })
    assert pred_res_name.status_code == 200
    pred_data_wheat = pred_res_name.get_json()["data"]
    assert pred_data_wheat["commodity"] == "Wheat"
    assert pred_data_wheat["commodity_code"] == "COM-WHT"

    # 3. Inventory alerts endpoint contains commodity_code
    inv_alerts_res = client.get("/api/inventory/alerts")
    assert inv_alerts_res.status_code == 200
    inv_alerts = inv_alerts_res.get_json()["data"]
    assert len(inv_alerts) > 0
    for alert in inv_alerts:
        assert "commodity_code" in alert
        assert alert["commodity_code"] in ["COM-RIC", "COM-WHT", "COM-SUG", "COM-DAL"]


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


def test_beneficiary_duplicate_prevention(client):
    """
    Verifies that duplicate beneficiary IDs and duplicate ration card numbers
    are rejected with 409 Conflict.
    """
    unique_id = f"TEST-DUP-{uuid.uuid4().hex[:6].upper()}"
    card_no = f"RC-DUP-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create initial beneficiary
    create_res = client.post("/api/beneficiaries", json={
        "beneficiary_id": unique_id,
        "name": "Duplicate Test Cardholder",
        "region": "Salem",
        "family_size": 3,
        "ration_card_type": "Priority (PHH)",
        "ration_card_number": card_no
    })
    assert create_res.status_code == 201

    try:
        # 2. Attempt duplicate beneficiary_id
        dup_id_res = client.post("/api/beneficiaries", json={
            "beneficiary_id": unique_id,
            "name": "Another Name",
            "region": "Chennai",
            "family_size": 4,
            "ration_card_type": "Priority (PHH)"
        })
        assert dup_id_res.status_code == 409
        assert "already exists" in dup_id_res.get_json()["message"]

        # 3. Attempt duplicate ration_card_number with different beneficiary_id
        other_id = f"TEST-DUP2-{uuid.uuid4().hex[:6].upper()}"
        dup_card_res = client.post("/api/beneficiaries", json={
            "beneficiary_id": other_id,
            "name": "Third Name",
            "region": "Madurai",
            "family_size": 2,
            "ration_card_type": "Priority (PHH)",
            "ration_card_number": card_no
        })
        assert dup_card_res.status_code == 409
        assert "already registered" in dup_card_res.get_json()["message"] or "already in use" in dup_card_res.get_json()["message"]
    finally:
        client.delete(f"/api/beneficiaries/{unique_id}")


def test_beneficiary_auto_generate_card_number_and_persistence(client):
    """
    Verifies that omitting ration_card_number generates a guaranteed unique card number,
    persists in MongoDB with computed monthly quotas, and matches configured rules.
    """
    from backend.database.mongo import get_db
    unique_id = f"TEST-GEN-{uuid.uuid4().hex[:6].upper()}"

    res = client.post("/api/beneficiaries", json={
        "beneficiary_id": unique_id,
        "name": "Auto Generation Cardholder",
        "region": "Tiruchirappalli",
        "family_size": 4,
        "ration_card_type": "Priority (PHH)"
        # ration_card_number omitted
    })
    assert res.status_code == 201
    data = res.get_json()["data"]

    # Verify generated card number
    assert "ration_card_number" in data
    assert data["ration_card_number"].startswith(f"RC-{unique_id}")

    # Verify database persistence in MongoDB
    db = get_db()
    db_doc = db.beneficiaries.find_one({"beneficiary_id": unique_id}, {"_id": 0})
    assert db_doc is not None
    assert db_doc["name"] == "Auto Generation Cardholder"
    assert db_doc["region"] == "Tiruchirappalli"
    assert db_doc["family_size"] == 4
    # Configured PHH rule: Rice = 4 * 5 = 20kg, Wheat = 4 * 2 = 8kg, Sugar = 1kg, Dal = 1kg
    assert db_doc["monthly_quota"]["Rice"] == 20.0
    assert db_doc["monthly_quota"]["Wheat"] == 8.0
    assert db_doc["monthly_quota"]["Sugar"] == 1.0
    assert db_doc["monthly_quota"]["Dal"] == 1.0

    # Clean up
    del_res = client.delete(f"/api/beneficiaries/{unique_id}")
    assert del_res.status_code == 200


def test_beneficiary_deletion_restriction_with_anomaly_alert(client):
    """
    Verifies that cardholders linked to active fraud/anomaly alerts
    (such as BEN004 with TXN-1006) cannot be deleted.
    """
    del_res = client.delete("/api/beneficiaries/BEN004")
    assert del_res.status_code == 409
    data = del_res.get_json()
    assert data["status"] == "error"
    assert "deletion blocked" in data["message"].lower() or "transaction" in data["message"].lower() or "anomaly" in data["message"].lower()

