from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from backend.database.mongo import get_db
from backend.services.inventory_service import InventoryService
from backend.services.ml_service import MLService
from backend.services.auth_service import token_required, role_required
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
@role_required("admin", "officer", "dealer")
def create_transaction():
    """
    Executes a PDS grain distribution transaction.
    1. Validates input payload and user authorization
    2. Verifies beneficiary exists in the registry
    3. Checks monthly entitlement quota for the commodity
    4. Guards against duplicate submissions within a short time window
    5. Runs Anomaly Detection ML model
    6. Thread-safely and atomically checks and deducts stock using InventoryService
    7. Records transaction and any suspicious alert
    """
    data = request.get_json(silent=True) or {}
    errors = validate_transaction_payload(data)
    if errors:
        return jsonify({"status": "error", "message": "; ".join(errors), "errors": errors}), 400

    beneficiary_id = data["beneficiary_id"].strip().upper()
    commodity_raw = (data.get("commodity") or data.get("commodity_code", "")).strip()
    quantity = float(data["quantity"])
    ration_shop_id = data.get("ration_shop_id", "FPS-CHN-001").strip()
    region = data.get("region", "Chennai").strip()

    # Canonical commodity resolution
    comm_upper = commodity_raw.upper()
    if comm_upper in ["COM-RIC", "RICE"]:
        resolved_comm = "Rice"
        commodity_code = "COM-RIC"
    elif comm_upper in ["COM-WHT", "WHEAT"]:
        resolved_comm = "Wheat"
        commodity_code = "COM-WHT"
    elif comm_upper in ["COM-SUG", "SUGAR"]:
        resolved_comm = "Sugar"
        commodity_code = "COM-SUG"
    elif comm_upper in ["COM-DAL", "DAL"]:
        resolved_comm = "Dal"
        commodity_code = "COM-DAL"
    else:
        resolved_comm = commodity_raw.capitalize()
        commodity_code = f"COM-{commodity_raw[:3].upper()}"

    user = getattr(request, "user", {})
    if user.get("role") == "dealer" and user.get("region"):
        if user["region"].lower() != region.lower():
            return jsonify({
                "status": "error",
                "message": f"Dealer authorization restricted to assigned district '{user['region']}'."
            }), 403

    db = get_db()

    # --- Step 1: Verify beneficiary exists ---
    ben = db.beneficiaries.find_one({"beneficiary_id": beneficiary_id})
    if not ben:
        return jsonify({
            "status": "error",
            "message": f"Beneficiary '{beneficiary_id}' not found in the registry. Please verify the ID."
        }), 404

    family_size = int(ben.get("family_size", 4))
    card_type = ben.get("ration_card_type", "Priority (PHH)")

    # --- Step 2: Monthly entitlement and remaining quota calculation ---
    from backend.models.beneficiary import BeneficiaryModel
    monthly_quota = ben.get("monthly_quota")
    if not monthly_quota:
        monthly_quota = BeneficiaryModel.calculate_monthly_quota(card_type, family_size)
    entitled_qty = float(monthly_quota.get(resolved_comm, 0.0))

    # Calculate already-distributed quantity for current calendar month
    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)
    past_month_txns = list(db.transactions.find({
        "beneficiary_id": beneficiary_id,
        "$or": [
            {"commodity": resolved_comm},
            {"commodity_code": commodity_code}
        ],
        "timestamp": {"$gte": start_of_month}
    }))
    already_drawn = round(sum(float(t.get("quantity", 0.0)) for t in past_month_txns), 2)
    remaining_entitlement = max(0.0, round(entitled_qty - already_drawn, 2))

    entitlement_warning = None
    if quantity > remaining_entitlement:
        if remaining_entitlement == 0.0:
            entitlement_warning = (
                f"Beneficiary {beneficiary_id} has already exhausted the monthly {resolved_comm} quota "
                f"({already_drawn} kg / {entitled_qty} kg drawn). Distribution exceeds monthly entitlement."
            )
        else:
            entitlement_warning = (
                f"Requested {quantity} kg exceeds monthly entitlement ({remaining_entitlement} kg remaining of {entitled_qty} kg quota, "
                f"{already_drawn} kg already collected this month)."
            )
        logger.warning(f"[Entitlement Warning] {beneficiary_id}: {entitlement_warning}")

    # --- Step 3: Duplicate submission guard (same beneficiary + commodity + region within 60s) ---
    recent_cutoff = datetime.utcnow() - timedelta(seconds=60)
    recent_dup = db.transactions.find_one({
        "beneficiary_id": beneficiary_id,
        "$or": [
            {"commodity": resolved_comm},
            {"commodity_code": commodity_code}
        ],
        "region": region,
        "timestamp": {"$gte": recent_cutoff}
    })
    if recent_dup:
        return jsonify({
            "status": "error",
            "message": (
                f"Duplicate submission detected. A transaction for {resolved_comm} was already "
                f"processed for {beneficiary_id} at this location within the last 60 seconds "
                f"(Txn: {recent_dup.get('transaction_id')}). Please wait before retrying."
            )
        }), 409

    # --- Step 4: Run ML Anomaly Detection ---
    anomaly_result = MLService.detect_anomaly({
        "beneficiary_id": beneficiary_id,
        "ration_shop_id": ration_shop_id,
        "commodity": resolved_comm,
        "commodity_code": commodity_code,
        "quantity": quantity,
        "family_size": family_size,
        "card_type": card_type,
        "region": region,
        "entitled_quota": entitled_qty,
        "remaining_entitlement": remaining_entitlement,
        "already_distributed": already_drawn
    })

    # If quantity exceeds remaining entitlement, ensure clear anomaly explanation
    if quantity > remaining_entitlement and anomaly_result.get("status") == "NORMAL":
        anomaly_result["status"] = "SUSPICIOUS"
        anomaly_result["risk_level"] = "MEDIUM" if quantity <= (entitled_qty * 1.5) else "HIGH"
        anomaly_result["reason"] = (
            f"Quantity ({quantity} kg) exceeds remaining monthly entitlement ({remaining_entitlement} kg) "
            f"by {round(quantity - remaining_entitlement, 1)} kg (Monthly quota: {entitled_qty} kg, already drawn: {already_drawn} kg)"
        )

    # --- Step 5: Thread-safe inventory deduction ---
    distribution_result = InventoryService.process_transaction_distribution(
        commodity=resolved_comm,
        region=region,
        quantity=quantity,
        beneficiary_id=beneficiary_id,
        ration_shop_id=ration_shop_id,
        anomaly_info=anomaly_result,
        entitlement_info={
            "entitled_quota": entitled_qty,
            "already_distributed": already_drawn,
            "remaining_entitlement": remaining_entitlement
        }
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
        "anomaly_analysis": anomaly_result,
        "entitlement_info": {
            "monthly_quota": entitled_qty,
            "already_distributed": already_drawn,
            "remaining_entitlement": remaining_entitlement
        }
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
        sf = status_filter.upper()
        if sf == "PENDING_REVIEW":
            filter_query["$or"] = [
                {"status": "PENDING_REVIEW"},
                {"status": {"$exists": False}},
                {"status": None}
            ]
        elif sf in ["VERIFIED_LEGITIMATE", "APPROVED_GENUINE"]:
            filter_query["status"] = {"$in": ["VERIFIED_LEGITIMATE", "APPROVED_GENUINE", "DISMISSED_FALSE_POSITIVE"]}
        elif sf in ["CONFIRMED_IRREGULARITY", "FLAGGED_FRAUD"]:
            filter_query["status"] = {"$in": ["CONFIRMED_IRREGULARITY", "FLAGGED_FRAUD"]}
        elif sf == "REVIEWED":
            filter_query["status"] = {"$in": ["REVIEWED", "VERIFIED_LEGITIMATE", "CONFIRMED_IRREGULARITY", "RESOLVED", "APPROVED_GENUINE", "FLAGGED_FRAUD"]}
        else:
            filter_query["status"] = sf
    if commodity and commodity.upper() != "ALL":
        filter_query["commodity"] = commodity

    alerts = list(db.fraud_alerts.find(filter_query, {"_id": 0}).sort("created_at", -1))
    
    # Calculate overall database totals (scoped by region/commodity if provided) for UI summary badges
    base_scope = {}
    if region:
        base_scope["region"] = region
    if commodity and commodity.upper() != "ALL":
        base_scope["commodity"] = commodity

    total_db_alerts = db.fraud_alerts.count_documents(base_scope)
    total_db_pending = db.fraud_alerts.count_documents({
        **base_scope,
        "$or": [
            {"status": "PENDING_REVIEW"},
            {"status": {"$exists": False}},
            {"status": None}
        ]
    })
    total_db_outliers = db.fraud_alerts.count_documents({
        **base_scope,
        "$or": [
            {"anomaly_score": {"$lt": 0}},
            {"risk_level": "HIGH"}
        ]
    })
    
    # Enrich score interpretations and verify detection reasons against actual transaction & beneficiary entitlements
    for a in alerts:
        score = float(a.get("anomaly_score", 0.0))
        if score < 0:
            a["score_interpretation"] = (
                f"Statistical Outlier ({score:.4f} < 0): Shorter tree isolation path indicating distribution deviation. "
                f"(Algorithmic distance measure, NOT a probability of fraud)."
            )
            a["score_badge"] = "SEVERE_ANOMALY" if score < -0.10 else "MILD_ANOMALY"
        else:
            a["score_interpretation"] = f"Normal Inlier ({score:.4f} >= 0): Conforms to expected distribution cluster."
            a["score_badge"] = "NORMAL_INLIER"

        # Verify detection reasons against beneficiary profile & entitlements if missing
        bid = a.get("beneficiary_id")
        comm = a.get("commodity", "Rice")
        qty = float(a.get("quantity", 0.0))
        if not a.get("entitled_quota") and bid:
            try:
                ben = db.beneficiaries.find_one({"beneficiary_id": bid})
                if ben:
                    quota = ben.get("monthly_quota", {}).get(comm)
                    if quota:
                        a["entitled_quota"] = float(quota)
                        a["quantity_to_quota_ratio"] = round(qty / float(quota), 2)
                        if not a.get("reason") or "exceeds" not in str(a.get("reason", "")).lower():
                            a["reason"] = f"Quantity ({qty} kg) exceeds monthly {comm} entitlement ({quota} kg) by {a['quantity_to_quota_ratio']}x"
            except Exception:
                pass

        # Format timestamps safely for frontend tables
        if "created_at" in a:
            if isinstance(a["created_at"], datetime):
                a["created_at_formatted"] = a["created_at"].strftime("%Y-%m-%d %H:%M")
                a["created_at"] = a["created_at"].isoformat()
            elif isinstance(a["created_at"], str):
                a["created_at_formatted"] = a["created_at"][:16].replace("T", " ")

        if "reviewed_at" in a and a["reviewed_at"]:
            if isinstance(a["reviewed_at"], datetime):
                a["reviewed_at_formatted"] = a["reviewed_at"].strftime("%Y-%m-%d %H:%M")
                a["reviewed_at"] = a["reviewed_at"].isoformat()
            elif isinstance(a["reviewed_at"], str):
                a["reviewed_at_formatted"] = a["reviewed_at"][:16].replace("T", " ")

    pending_alerts = [a for a in alerts if a.get("status", "PENDING_REVIEW") == "PENDING_REVIEW"]
    
    return jsonify({
        "status": "success",
        "total": len(alerts),
        "count": len(pending_alerts),
        "pending_count": len(pending_alerts),
        "total_records": total_db_alerts,
        "total_pending": total_db_pending,
        "total_outliers": total_db_outliers if total_db_outliers > 0 else total_db_alerts,
        "data": alerts,
        "audit_principle": "Statistical anomalies alone do NOT constitute unilateral proof of fraud. Human officer verification required."
    }), 200


@transaction_bp.route("/fraud-alerts/<transaction_id>/review", methods=["POST"])
@role_required("admin", "officer")
def review_fraud_alert(transaction_id):
    """
    Submits an official auditable review decision by an authorized officer.
    Records officer ID, timestamp, decision, and audit reason/comments without altering original transaction metrics.
    Review statuses: Pending Review, Verified Legitimate, and Confirmed Irregularity.
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
    reason = str(data.get("reason") or data.get("comments") or "").strip()

    valid_decisions = [
        "VERIFIED_LEGITIMATE",
        "CONFIRMED_IRREGULARITY",
        "PENDING_REVIEW",
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

    if decision in ["VERIFIED_LEGITIMATE", "APPROVED_GENUINE", "DISMISSED_FALSE_POSITIVE"]:
        standard_status = "VERIFIED_LEGITIMATE"
    elif decision in ["CONFIRMED_IRREGULARITY", "FLAGGED_FRAUD"]:
        standard_status = "CONFIRMED_IRREGULARITY"
    elif decision == "PENDING_REVIEW":
        standard_status = "PENDING_REVIEW"
    elif decision == "REQUIRES_INSPECTION":
        standard_status = "REQUIRES_INSPECTION"
    else:
        standard_status = "REVIEWED"

    reviewed_at = datetime.utcnow()
    review_record = {
        "officer_id": officer_id,
        "decision": decision,
        "standard_status": standard_status,
        "reason": reason,
        "comments": reason,
        "reviewed_at": reviewed_at,
        "reviewed_at_iso": reviewed_at.isoformat(),
        "previous_status": alert.get("status", "PENDING_REVIEW")
    }

    # 1. Update fraud alert document with review decision and standard status
    db.fraud_alerts.update_one(
        {"transaction_id": tid},
        {
            "$set": {
                "status": standard_status,
                "review_decision": decision,
                "review_reason": reason,
                "comments": reason,
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
                "review_status": standard_status,
                "review_decision": decision,
                "reviewed_by": officer_id,
                "reviewed_at": reviewed_at,
                "review_reason": reason,
                "review_comments": reason
            },
            "$push": {
                "audit_trail": {
                    "action": "ADMINISTRATIVE_FRAUD_REVIEW",
                    "officer_id": officer_id,
                    "decision": decision,
                    "standard_status": standard_status,
                    "reason": reason,
                    "comments": reason,
                    "timestamp": reviewed_at,
                    "preserved_quantity": alert.get("quantity"),
                    "preserved_anomaly_score": alert.get("anomaly_score")
                }
            }
        }
    )

    logger.info(f"[Audit Review] Alert {tid} reviewed by {officer_id}: Decision={decision} (Status={standard_status}), Reason={reason}")

    return jsonify({
        "status": "success",
        "message": f"Audit review for '{tid}' submitted successfully",
        "data": {
            "transaction_id": tid,
            "decision": decision,
            "status": standard_status,
            "officer_id": officer_id,
            "reviewed_at": reviewed_at.isoformat(),
            "reason": reason,
            "comments": reason
        }
    }), 200


@transaction_bp.route("/fraud-alerts/<transaction_id>/resolve", methods=["POST", "PUT"])
@role_required("admin", "officer")
def resolve_fraud_alert(transaction_id):
    """Marks a flagged suspicious alert as reviewed/resolved by the officer (retained for backward compatibility)."""
    data = request.get_json(silent=True) or {}
    if not data.get("reason"):
        data["reason"] = data.get("resolution_notes") or "Officer verified and approved transaction."
    if not data.get("decision"):
        data["decision"] = "VERIFIED_LEGITIMATE"
    if not data.get("officer_id"):
        data["officer_id"] = "admin"
    
    # Forward to the auditable review handler
    return review_fraud_alert(transaction_id)

