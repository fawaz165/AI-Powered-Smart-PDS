import pytest
from backend.app import create_app
from backend.database.mongo import get_db
from backend.services.auth_service import AuthService


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_tokens(client):
    """Generates authentic tokens for Admin, District Officer, and FPS Dealer."""
    admin_token = AuthService.generate_token({"username": "admin", "role": "admin"})
    officer_token = AuthService.generate_token({"username": "officer_chennai", "role": "officer", "region": "Chennai"})
    dealer_token = AuthService.generate_token({"username": "dealer_001", "role": "dealer", "region": "Chennai", "ration_shop_id": "FPS-CHN-001"})
    return {
        "admin": admin_token,
        "officer": officer_token,
        "dealer": dealer_token
    }


def test_rbac_commodity_catalog_restrictions(client, auth_tokens):
    """
    RBAC Test 1: Only Admin can create or modify commodities.
    District Officers and FPS Dealers must be rejected with 403 Forbidden.
    """
    payload = {
        "commodity_code": "COM-RBAC-TEST",
        "name": "RBAC Test Millet",
        "unit": "kg",
        "subsidized_price": 2.0,
        "market_price": 30.0,
        "rate_type": "STATE_SUBSIDY"
    }

    # 1. FPS Dealer attempting to create commodity -> 403 Forbidden
    res_dealer = client.post(
        "/api/commodities",
        json=payload,
        headers={"Authorization": f"Bearer {auth_tokens['dealer']}"}
    )
    assert res_dealer.status_code == 403
    assert "Access denied" in res_dealer.get_json()["message"]

    # 2. District Officer attempting to create commodity -> 403 Forbidden
    res_officer = client.post(
        "/api/commodities",
        json=payload,
        headers={"Authorization": f"Bearer {auth_tokens['officer']}"}
    )
    assert res_officer.status_code == 403
    assert "Access denied" in res_officer.get_json()["message"]

    # 3. Admin creating commodity -> 201 Created
    res_admin = client.post(
        "/api/commodities",
        json=payload,
        headers={"Authorization": f"Bearer {auth_tokens['admin']}"}
    )
    assert res_admin.status_code == 201

    # Cleanup
    db = get_db()
    db.commodities.delete_one({"commodity_code": "COM-RBAC-TEST"})


def test_rbac_fraud_review_restrictions(client, auth_tokens):
    """
    RBAC Test 2: FPS Dealers cannot review fraud alerts.
    Only Admin and District Officers are authorized.
    """
    db = get_db()
    txn_id = "TXN-RBAC-TEST-001"
    db.fraud_alerts.update_one(
        {"transaction_id": txn_id},
        {"$set": {
            "transaction_id": txn_id,
            "beneficiary_id": "BEN001",
            "commodity": "Rice",
            "quantity": 90.0,
            "region": "Chennai",
            "status": "PENDING_REVIEW",
            "risk_level": "HIGH",
            "reason": "Excessive withdrawal",
            "review_history": []
        }},
        upsert=True
    )

    review_payload = {
        "officer_id": "DEALER-OFFICER-X",
        "decision": "VERIFIED_LEGITIMATE",
        "reason": "Attempted self-clearing by dealer"
    }

    # 1. FPS Dealer attempting fraud review -> 403 Forbidden
    res_dealer = client.post(
        f"/api/transactions/fraud-alerts/{txn_id}/review",
        json=review_payload,
        headers={"Authorization": f"Bearer {auth_tokens['dealer']}"}
    )
    assert res_dealer.status_code == 403
    assert "Access denied" in res_dealer.get_json()["message"]

    # 2. District Officer performing fraud review -> 200 OK
    officer_payload = {
        "officer_id": "DSO-CHENNAI-01",
        "decision": "VERIFIED_LEGITIMATE",
        "reason": "Authorized festival family allocation verified by district supply office."
    }
    res_officer = client.post(
        f"/api/transactions/fraud-alerts/{txn_id}/review",
        json=officer_payload,
        headers={"Authorization": f"Bearer {auth_tokens['officer']}"}
    )
    assert res_officer.status_code == 200
    assert res_officer.get_json()["data"]["status"] == "VERIFIED_LEGITIMATE"

    # Cleanup
    db.fraud_alerts.delete_one({"transaction_id": txn_id})


def test_forecast_history_and_reliable_confidence_range(client):
    """
    Verifies that demand predictions include mathematically reliable 95% confidence ranges,
    actual demand comparisons, and that /api/predictions/history returns past predictions.
    """
    pred_payload = {
        "commodity": "Rice",
        "region": "Chennai",
        "month": 11,
        "year": 2026,
        "beneficiary_count": 12500,
        "current_stock": 3800.0,
        "safety_stock": 500.0,
        "previous_demand": 4200.0,
        "is_custom_scenario": False
    }

    # 1. Trigger prediction
    res_pred = client.post("/api/predict-demand", json=pred_payload)
    assert res_pred.status_code == 200
    data = res_pred.get_json()["data"]

    # Verify confidence range
    assert "confidence_range" in data
    cr = data["confidence_range"]
    assert cr["confidence_level"] == "95%"
    assert cr["lower_bound_kg"] < data["predicted_demand"]
    assert cr["upper_bound_kg"] > data["predicted_demand"]
    assert cr["margin_of_error_kg"] == 799.2  # 1.96 * 407.78
    assert "formatted_range" in cr

    # Verify actual demand comparison structure
    assert "actual_comparison" in data
    assert "comparison_summary" in data["actual_comparison"]

    # 2. Fetch forecast history
    res_hist = client.get("/api/predictions/history?region=Chennai&commodity=Rice")
    assert res_hist.status_code == 200
    hist_data = res_hist.get_json()
    assert hist_data["status"] == "success"
    assert isinstance(hist_data["data"], list)
    assert len(hist_data["data"]) >= 1

    latest = hist_data["data"][0]
    assert latest["commodity"] == "Rice"
    assert latest["region"] == "Chennai"
    assert "predicted_demand" in latest
    assert "model_used" in latest

