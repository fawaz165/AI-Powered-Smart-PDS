from flask import Blueprint, request, jsonify
from backend.database.mongo import get_db
from backend.services.inventory_service import InventoryService
from backend.services.ml_service import MLService
from backend.utils.validators import validate_transaction_payload
from backend.utils.logger import logger

transaction_bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")


@transaction_bp.route("", methods=["GET"])
def list_transactions():
    """Lists recent distribution transactions with filtering and pagination."""
    db = get_db()
    query = {}
    beneficiary_id = request.args.get("beneficiary_id")
    commodity = request.args.get("commodity")
    status = request.args.get("status")
    region = request.args.get("region")

    if beneficiary_id:
        query["beneficiary_id"] = beneficiary_id.strip().upper()
    if commodity:
        query["commodity"] = commodity
    if status:
        query["status"] = status
    if region:
        query["region"] = region

    limit = int(request.args.get("limit", 50))
    skip = int(request.args.get("skip", 0))

    txns = list(db.transactions.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit))
    total_count = db.transactions.count_documents(query)

    return jsonify({
        "status": "success",
        "total": total_count,
        "count": len(txns),
        "data": txns
    }), 200


@transaction_bp.route("/<transaction_id>", methods=["GET"])
def get_transaction(transaction_id):
    """Fetches details of a specific transaction."""
    db = get_db()
    tid = transaction_id.strip().upper()
    txn = db.transactions.find_one({"transaction_id": tid}, {"_id": 0})
    if not txn:
        return jsonify({"status": "error", "message": f"Transaction '{tid}' not found"}), 404
    return jsonify({"status": "success", "data": txn}), 200


@transaction_bp.route("", methods=["POST"])
def create_transaction():
    """
    Executes a PDS grain distribution transaction.
    1. Validates input
    2. Runs Anomaly Detection ML model
    3. Thread-safely checks and deducts stock using InventoryService
    4. Records transaction and any suspicious alert
    """
    data = request.get_json(silent=True) or {}
    errors = validate_transaction_payload(data)
    if errors:
        return jsonify({"status": "error", "errors": errors}), 400

    beneficiary_id = data["beneficiary_id"].strip().upper()
    commodity = data["commodity"].strip()
    quantity = float(data["quantity"])
    ration_shop_id = data.get("ration_shop_id", "FPS-CHN-001").strip()
    region = data.get("region", "Chennai").strip()

    db = get_db()
    # Check if beneficiary exists
    ben = db.beneficiaries.find_one({"beneficiary_id": beneficiary_id})
    family_size = ben.get("family_size", 4) if ben else 4
    card_type = ben.get("ration_card_type", "Priority (PHH)") if ben else "Priority (PHH)"

    # Run ML Anomaly Detection on this incoming transaction
    anomaly_result = MLService.detect_anomaly({
        "beneficiary_id": beneficiary_id,
        "ration_shop_id": ration_shop_id,
        "commodity": commodity,
        "quantity": quantity,
        "family_size": family_size,
        "card_type": card_type,
        "region": region
    })

    # Execute thread-safe inventory deduction
    distribution_result = InventoryService.process_transaction_distribution(
        commodity=commodity,
        region=region,
        quantity=quantity,
        beneficiary_id=beneficiary_id,
        ration_shop_id=ration_shop_id,
        anomaly_info=anomaly_result
    )

    if not distribution_result.get("success"):
        return jsonify({
            "status": "error",
            "message": distribution_result.get("message"),
            "details": distribution_result
        }), 400

    return jsonify({
        "status": "success",
        "message": "Transaction distributed and recorded successfully",
        "data": distribution_result,
        "anomaly_analysis": anomaly_result
    }), 201


@transaction_bp.route("/fraud-alerts", methods=["GET"])
def list_fraud_alerts():
    """Returns all flagged suspicious transactions requiring administrative review."""
    db = get_db()
    alerts = list(db.fraud_alerts.find({}, {"_id": 0}).sort("created_at", -1))
    return jsonify({
        "status": "success",
        "count": len(alerts),
        "data": alerts
    }), 200
