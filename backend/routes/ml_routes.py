from flask import Blueprint, request, jsonify
from backend.services.ml_service import MLService
from backend.utils.logger import logger

ml_bp = Blueprint("ml", __name__, url_prefix="/api")


@ml_bp.route("/predict-demand", methods=["POST"])
def predict_demand_endpoint():
    """
    ML Demand Prediction API Endpoint.
    Input example:
    {
      "commodity": "Rice",
      "region": "Chennai",
      "beneficiary_count": 12500,
      "previous_demand": 4200,
      "current_stock": 3800,
      "month": 11
    }
    Output:
    {
      "commodity": "Rice",
      "predicted_demand": 4500,
      "current_stock": 3800,
      "shortage": 700,
      "recommended_procurement": 700,
      "status": "SHORTAGE"
    }
    """
    data = request.get_json(silent=True) or {}
    
    # Input validation
    if not data.get("commodity"):
        return jsonify({"status": "error", "message": "commodity is required"}), 400
    if not data.get("region"):
        return jsonify({"status": "error", "message": "region is required"}), 400

    try:
        prediction_result = MLService.predict_demand(data)
        logger.info(
            f"Demand predicted: {prediction_result['commodity']} in {prediction_result['region']} "
            f"-> {prediction_result['predicted_demand']} kg (Stock: {prediction_result['current_stock']} kg)"
        )
        return jsonify({
            "status": "success",
            "data": prediction_result
        }), 200

    except Exception as e:
        logger.error(f"Demand prediction failed: {e}")
        return jsonify({
            "status": "error",
            "message": f"Demand prediction calculation error: {str(e)}"
        }), 500


@ml_bp.route("/detect-anomaly", methods=["POST"])
def detect_anomaly_endpoint():
    """
    ML Anomaly Detection API Endpoint.
    Input:
    {
      "beneficiary_id": "BEN001",
      "commodity": "Rice",
      "quantity": 95,
      "family_size": 4,
      "card_type": "Priority (PHH)"
    }
    Output:
    {
      "status": "SUSPICIOUS",
      "risk_level": "HIGH",
      "anomaly_score": -0.28,
      "reason": "Unusually high quantity compared with historical entitlement"
    }
    """
    data = request.get_json(silent=True) or {}
    if not data.get("commodity") or data.get("quantity") is None:
        return jsonify({"status": "error", "message": "commodity and quantity are required"}), 400

    try:
        anomaly_result = MLService.detect_anomaly(data)
        return jsonify({
            "status": "success",
            "data": anomaly_result
        }), 200
    except Exception as e:
        logger.error(f"Anomaly detection failed: {e}")
        return jsonify({
            "status": "error",
            "message": f"Anomaly detection calculation error: {str(e)}"
        }), 500


@ml_bp.route("/model-metrics", methods=["GET"])
def get_metrics_endpoint():
    """Returns comparative model benchmark evaluation metrics (MAE, MSE, RMSE, R²)."""
    metrics = MLService.get_model_metrics()
    return jsonify({
        "status": "success",
        "data": metrics
    }), 200
