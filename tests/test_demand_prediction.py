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
