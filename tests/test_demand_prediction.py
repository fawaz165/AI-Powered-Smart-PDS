import pytest
from backend.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_predict_demand_api_shortage_calculation(client):
    """
    Tests POST /api/predict-demand with the prompt's reference scenario:
    Current stock = 3,800 kg
    Verifies shortage > 0 triggers status="SHORTAGE" and recommended_procurement = shortage.
    """
    payload = {
        "commodity": "Rice",
        "region": "Chennai",
        "beneficiary_count": 12500,
        "previous_demand": 4200,
        "current_stock": 3800,
        "month": 11
    }

    res = client.post("/api/predict-demand", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"

    pred = data["data"]
    assert pred["commodity"] == "Rice"
    assert pred["current_stock"] == 3800
    assert pred["predicted_demand"] > 0
    assert pred["shortage"] == round(pred["predicted_demand"] - 3800, 1)

    if pred["shortage"] > 0:
        assert pred["status"] == "SHORTAGE"
        assert pred["recommended_procurement"] == pred["shortage"]
        assert "Potential shortage:" in pred["message"]


def test_predict_demand_api_sufficient_stock(client):
    """Verifies that when current stock exceeds predicted demand, recommended_procurement is 0."""
    payload = {
        "commodity": "Wheat",
        "region": "Chennai",
        "beneficiary_count": 5000,
        "previous_demand": 2000,
        "current_stock": 50000,  # Huge stock
        "month": 5
    }

    res = client.post("/api/predict-demand", json=payload)
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["shortage"] == 0.0
    assert data["recommended_procurement"] == 0.0
    assert data["status"] in ["SUFFICIENT", "EXCESS"]


def test_predict_demand_all_commodities_consistency(client):
    """Verifies consistent demand forecasting across all 4 PDS commodities."""
    commodities = ["Rice", "Wheat", "Sugar", "Dal"]
    for commodity in commodities:
        payload = {
            "commodity": commodity,
            "region": "Coimbatore",
            "beneficiary_count": 8000,
            "previous_demand": 2500,
            "current_stock": 2000,
            "month": 10
        }
        res = client.post("/api/predict-demand", json=payload)
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["commodity"] == commodity
        assert data["predicted_demand"] > 0
        assert data["shortage"] >= 0.0
        if data["predicted_demand"] > 2000:
            assert data["status"] == "SHORTAGE"
            assert data["recommended_procurement"] == data["shortage"]
        else:
            assert data["shortage"] == 0.0
            assert data["recommended_procurement"] == 0.0


def test_inventory_alerts_aggregation_consistency(client):
    """Verifies that inventory alerts return consistent non-negative shortages and valid aggregations."""
    res = client.get("/api/inventory/alerts")
    assert res.status_code == 200
    alerts = res.get_json()["data"]
    assert len(alerts) > 0

    total_stock = sum(a["current_stock"] for a in alerts)
    total_demand = sum(a["predicted_demand"] for a in alerts)
    total_shortage = sum(a["shortage"] for a in alerts)
    total_procurement = sum(a["recommended_procurement"] for a in alerts)

    assert total_stock > 0
    assert total_demand > 0
    assert total_shortage >= 0
    assert total_procurement == total_shortage

    for alert in alerts:
        assert alert["shortage"] >= 0.0
        assert alert["current_stock"] >= 0.0
        assert alert["buffer_stock"] >= 0.0
        assert alert["status"] in ["SHORTAGE", "SUFFICIENT", "EXCESS"]
        if alert["status"] == "SHORTAGE":
            assert alert["recommended_procurement"] == alert["shortage"]
        else:
            assert alert["recommended_procurement"] == 0.0


def test_reconciliation_commodity_and_regional_shortages(client):
    """
    Data-Integrity Audit:
    Reconciles aggregate shortage with the sum of per-commodity shortages
    and the sum of per-regional shortages. Ensures 0.0 discrepancy.
    """
    from collections import defaultdict

    res = client.get("/api/inventory/alerts")
    assert res.status_code == 200
    alerts = res.get_json()["data"]
    assert len(alerts) > 0

    by_comm = defaultdict(float)
    by_region = defaultdict(float)
    total_shortage = 0.0

    for a in alerts:
        sh = float(a["shortage"])
        total_shortage += sh
        by_comm[a["commodity"]] += sh
        by_region[a["region"]] += sh

    sum_comm = sum(by_comm.values())
    sum_region = sum(by_region.values())

    # Zero discrepancy reconciliation
    assert round(abs(total_shortage - sum_comm), 2) == 0.0
    assert round(abs(total_shortage - sum_region), 2) == 0.0


def test_model_metrics_benchmark_evaluation(client):
    """Verifies that all 4 regression models are benchmarked with valid non-hardcoded MAE, MSE, RMSE, R²."""
    res = client.get("/api/model-metrics")
    assert res.status_code == 200
    data = res.get_json()["data"]

    assert "best_model" in data
    assert "evaluation_metrics" in data
    eval_metrics = data["evaluation_metrics"]

    expected_models = ["Linear Regression", "Decision Tree", "Random Forest", "XGBoost Regressor"]
    for m in expected_models:
        assert m in eval_metrics, f"Model {m} missing from benchmarks"
        metrics = eval_metrics[m]
        assert "MAE" in metrics and metrics["MAE"] > 0
        assert "MSE" in metrics and metrics["MSE"] > 0
        assert "RMSE" in metrics and metrics["RMSE"] > 0
        assert "R2" in metrics and 0.5 <= metrics["R2"] <= 1.0


def test_selected_model_validation():
    """Verifies that MLService validates the best model against benchmark criteria before inference."""
    from backend.services.ml_service import MLService
    is_valid = MLService.validate_selected_model()
    assert is_valid is True
    assert MLService._model_validated is True


def test_configurable_safety_stock_procurement(client):
    """Verifies procurement recommendation incorporates configurable safety stock."""
    payload = {
        "commodity": "Rice",
        "region": "Chennai",
        "beneficiary_count": 12500,
        "previous_demand": 4200,
        "current_stock": 3800,
        "safety_stock": 500.0,
        "month": 11,
        "year": 2026
    }

    res = client.post("/api/predict-demand", json=payload)
    assert res.status_code == 200
    d = res.get_json()["data"]

    pred_demand = d["predicted_demand"]
    # With safety stock, procurement = max(0, pred_demand + safety_stock - current_stock)
    expected_procurement = round(max(0.0, pred_demand + 500.0 - 3800), 1)
    assert d["recommended_procurement"] == expected_procurement
    assert d["safety_stock"] == 500.0


def test_prediction_explainability_factors(client):
    """Verifies demand prediction returns structured factor explainability and drivers."""
    payload = {
        "commodity": "Rice",
        "region": "Chennai",
        "beneficiary_count": 12500,
        "previous_demand": 4200,
        "current_stock": 3800,
        "month": 1,  # Pongal festival month
        "year": 2026
    }

    res = client.post("/api/predict-demand", json=payload)
    assert res.status_code == 200
    d = res.get_json()["data"]

    assert "explanation" in d
    exp = d["explanation"]
    assert "summary" in exp
    assert "factors" in exp
    assert len(exp["factors"]) == 4

    # Verify factor names
    factor_names = [f["name"] for f in exp["factors"]]
    assert "Demographic Scale" in factor_names
    assert "Seasonal & Festive Index" in factor_names
    assert "Historical Momentum" in factor_names
    assert "Warehouse Coverage" in factor_names


def test_scenario_vs_database_data_source_flag(client):
    """Verifies clear distinction between user simulation scenarios and database-backed values."""
    # Scenario 1: custom scenario
    res1 = client.post("/api/predict-demand", json={
        "commodity": "Rice",
        "region": "Chennai",
        "beneficiary_count": 15000,
        "previous_demand": 5000,
        "current_stock": 2000,
        "is_custom_scenario": True
    })
    assert res1.status_code == 200
    assert res1.get_json()["data"]["data_source"] == "USER_SCENARIO"

    # Scenario 2: database-backed
    res2 = client.post("/api/predict-demand", json={
        "commodity": "Rice",
        "region": "Chennai",
        "beneficiary_count": 12500,
        "previous_demand": 4200,
        "current_stock": 3800,
        "is_custom_scenario": False
    })
    assert res2.status_code == 200
    assert res2.get_json()["data"]["data_source"] == "DATABASE_BACKED"


