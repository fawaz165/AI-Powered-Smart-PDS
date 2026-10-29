from datetime import datetime, timedelta
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
    1. Validates input payload
    2. Verifies beneficiary exists in the registry
    3. Checks monthly entitlement quota for the commodity
    4. Guards against duplicate submissions within a short time window
    5. Runs Anomaly Detection ML model
    6. Thread-safely checks and deducts stock using InventoryService
    7. Records transaction and any suspicious alert
    """
    data = request.get_json(silent=True) or {}
    errors = validate_transaction_payload(data)
    if errors:
        return jsonify({"status": "error", "message": "; ".join(errors), "errors": errors}), 400

    beneficiary_id = data["beneficiary_id"].strip().upper()
    commodity = (data.get("commodity") or data.get("commodity_code", "")).strip()
    quantity = float(data["quantity"])
    ration_shop_id = data.get("ration_shop_id", "FPS-CHN-001").strip()
    region = data.get("region", "Chennai").strip()

    db = get_db()

    # --- Step 1: Verify beneficiary exists ---
    ben = db.beneficiaries.find_one({"beneficiary_id": beneficiary_id})
    if not ben:
        return jsonify({
            "status": "error",
            "message": f"Beneficiary '{beneficiary_id}' not found in the registry. Please verify the ID."
        }), 404

    family_size = ben.get("family_size", 4)
    card_type = ben.get("ration_card_type", "Priority (PHH)")

    # --- Step 2: Monthly entitlement quota check ---
    monthly_quota = ben.get("monthly_quota", {})
    entitled_qty = monthly_quota.get(commodity)
    entitlement_warning = None
    if entitled_qty is not None and quantity > entitled_qty:
        entitlement_warning = (
            f"Requested {quantity} kg exceeds monthly entitlement of {entitled_qty} kg "
            f"for {commodity} (card type: {card_type}). "
            f"Transaction will proceed but may be flagged."
        )
        logger.warning(f"[Entitlement] {beneficiary_id}: {entitlement_warning}")

    # --- Step 3: Duplicate submission guard (same beneficiary + commodity + region within 60s) ---
    recent_cutoff = datetime.utcnow() - timedelta(seconds=60)
    recent_dup = db.transactions.find_one({
        "beneficiary_id": beneficiary_id,
        "commodity": commodity,
        "region": region,
        "timestamp": {"$gte": recent_cutoff}
    })
    if recent_dup:
        return jsonify({
            "status": "error",
            "message": (
                f"Duplicate submission detected. A transaction for {commodity} was already "
                f"processed for {beneficiary_id} at this location within the last 60 seconds "
                f"(Txn: {recent_dup.get('transaction_id')}). Please wait before retrying."
            )
        }), 409

    # --- Step 4: Run ML Anomaly Detection ---
    anomaly_result = MLService.detect_anomaly({
        "beneficiary_id": beneficiary_id,
        "ration_shop_id": ration_shop_id,
        "commodity": commodity,
        "quantity": quantity,
        "family_size": family_size,
        "card_type": card_type,
        "region": region
    })

    # --- Step 5: Thread-safe inventory deduction ---
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

    response_data = {
        "status": "success",
        "message": "Transaction distributed and recorded successfully",
        "data": distribution_result,
        "anomaly_analysis": anomaly_result
    }
    if entitlement_warning:
        response_data["entitlement_warning"] = entitlement_warning

    return jsonify(response_data), 201


@transaction_bp.route("/fraud-alerts", methods=["GET"])
def list_fraud_alerts():
    """Returns all flagged suspicious transactions requiring administrative review with optional filters."""
    db = get_db()
    
    region = request.args.get("region", "").strip()
    risk_level = request.args.get("risk_level", "").strip()
    status_filter = request.args.get("status", "").strip()
    commodity = request.args.get("commodity", "").strip()

    filter_query = {}
    if region:
        filter_query["region"] = region
    if risk_level and risk_level.upper() != "ALL":
        filter_query["risk_level"] = risk_level.upper()
    if status_filter and status_filter.upper() != "ALL":
        filter_query["status"] = status_filter.upper()
    if commodity and commodity.upper() != "ALL":
        filter_query["commodity"] = commodity

    alerts = list(db.fraud_alerts.find(filter_query, {"_id": 0}).sort("created_at", -1))
    
    # Enrich score interpretations if not already stored
    for a in alerts:
        score = a.get("anomaly_score", 0.0)
        if not a.get("score_interpretation"):
            if score >= 0.05:
                a["score_interpretation"] = "Strong Inlier: Within normative cardholder distribution behavior."
                a["score_badge"] = "NORMAL_INLIER"
            elif score >= 0.0:
                a["score_interpretation"] = "Moderate Inlier: Conforms to expected distribution profile near baseline."
                a["score_badge"] = "BORDERLINE_NORMAL"
            elif score >= -0.10:
                a["score_interpretation"] = "Mild Outlier: Noticeable statistical deviation in draw quantity or frequency."
                a["score_badge"] = "MILD_ANOMALY"
            else:
                a["score_interpretation"] = "Severe Outlier: Short isolation path in tree ensemble indicating extreme deviation."
                a["score_badge"] = "SEVERE_ANOMALY"

    pending_alerts = [a for a in alerts if a.get("status", "PENDING_REVIEW") == "PENDING_REVIEW"]
    
    return jsonify({
        "status": "success",
        "total": len(alerts),
        "count": len(pending_alerts),
        "pending_count": len(pending_alerts),
        "data": alerts,
        "audit_principle": "Statistical anomalies alone do NOT constitute unilateral proof of fraud. Human officer verification required."
    }), 200


@transaction_bp.route("/fraud-alerts/<transaction_id>/review", methods=["POST"])
def review_fraud_alert(transaction_id):
    """
    Submits an official auditable review decision by an officer.
    Records officer ID, timestamp, decision, and audit reason without altering original transaction metrics.
    """
    db = get_db()
    tid = transaction_id.strip().upper()
    
    alert = db.fraud_alerts.find_one({"transaction_id": tid})
    if not alert:
        return jsonify({"status": "error", "message": f"Fraud alert for transaction '{tid}' not found"}), 404

    data = request.get_json(silent=True) or {}
    officer_id = str(data.get("officer_id") or "").strip()
    if not officer_id:
        return jsonify({
            "status": "error",
            "message": "Officer ID is required for auditable review decisions."
        }), 400

    decision = str(data.get("decision") or "").strip().upper()
    reason = str(data.get("reason") or "").strip()

    valid_decisions = [
        "APPROVED_GENUINE",
        "FLAGGED_FRAUD",
        "DISMISSED_FALSE_POSITIVE",
        "REQUIRES_INSPECTION",
        "RESOLVED"
    ]
    if decision not in valid_decisions:
        return jsonify({
            "status": "error",
            "message": f"Invalid review decision '{decision}'. Must be one of: {', '.join(valid_decisions)}"
        }), 400

    if len(reason) < 3:
        return jsonify({
            "status": "error",
            "message": "Audit reason / rationale is required (minimum 3 characters)."
        }), 400

    reviewed_at = datetime.utcnow()
    review_record = {
        "officer_id": officer_id,
        "decision": decision,
        "reason": reason,
        "reviewed_at": reviewed_at,
        "previous_status": alert.get("status", "PENDING_REVIEW")
    }

    # 1. Update fraud alert document
    db.fraud_alerts.update_one(
        {"transaction_id": tid},
        {
            "$set": {
                "status": "REVIEWED" if decision != "RESOLVED" else "RESOLVED",
                "review_decision": decision,
                "review_reason": reason,
                "reviewed_by": officer_id,
                "reviewed_at": reviewed_at
            },
            "$push": {
                "review_history": review_record
            }
        }
    )

    # 2. Append review decision to transaction audit trail without altering transaction quantity or anomaly score
    db.transactions.update_one(
        {"transaction_id": tid},
        {
            "$set": {
                "review_status": decision,
                "reviewed_by": officer_id,
                "reviewed_at": reviewed_at
            },
            "$push": {
                "audit_trail": {
                    "action": "ADMINISTRATIVE_FRAUD_REVIEW",
                    "officer_id": officer_id,
                    "decision": decision,
                    "reason": reason,
                    "timestamp": reviewed_at
                }
            }
        }
    )

    logger.info(f"[Audit Review] Alert {tid} reviewed by {officer_id}: Decision={decision}, Reason={reason}")

    return jsonify({
        "status": "success",
        "message": f"Audit review for '{tid}' submitted successfully",
        "data": {
            "transaction_id": tid,
            "decision": decision,
            "officer_id": officer_id,
            "reviewed_at": reviewed_at.isoformat(),
            "reason": reason
        }
    }), 200


@transaction_bp.route("/fraud-alerts/<transaction_id>/resolve", methods=["POST", "PUT"])
def resolve_fraud_alert(transaction_id):
    """Marks a flagged suspicious alert as reviewed/resolved by the officer (retained for backward compatibility)."""
    data = request.get_json(silent=True) or {}
    if not data.get("reason"):
        data["reason"] = "Officer verified and approved transaction."
    if not data.get("decision"):
        data["decision"] = "APPROVED_GENUINE"
    if not data.get("officer_id"):
        data["officer_id"] = "admin"
    
    # Forward to the auditable review handler
    return review_fraud_alert(transaction_id)

