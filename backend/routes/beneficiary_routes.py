from flask import Blueprint, request, jsonify
from datetime import datetime
from backend.database.mongo import get_db
from backend.models.beneficiary import BeneficiaryModel
from backend.services.auth_service import token_required
from backend.utils.validators import validate_beneficiary_payload
from backend.utils.logger import logger

beneficiary_bp = Blueprint("beneficiaries", __name__, url_prefix="/api/beneficiaries")


@beneficiary_bp.route("", methods=["GET"])
def list_beneficiaries():
    """Lists all beneficiaries with optional filtering by region, card type, and search query."""
    db = get_db()
    query = {}
    region = request.args.get("region")
    card_type = request.args.get("ration_card_type")
    search = request.args.get("search")

    if region:
        query["region"] = region.strip()
    if card_type:
        query["ration_card_type"] = card_type.strip()
    if search:
        search_str = search.strip()
        query["$or"] = [
            {"name": {"$regex": search_str, "$options": "i"}},
            {"beneficiary_id": {"$regex": search_str, "$options": "i"}},
            {"ration_card_number": {"$regex": search_str, "$options": "i"}}
        ]

    limit = int(request.args.get("limit", 100))
    skip = int(request.args.get("skip", 0))

    cursor = db.beneficiaries.find(query, {"_id": 0}).sort("beneficiary_id", 1).skip(skip).limit(limit)
    beneficiaries = list(cursor)
    total_count = db.beneficiaries.count_documents(query)

    return jsonify({
        "status": "success",
        "total": total_count,
        "count": len(beneficiaries),
        "data": beneficiaries
    }), 200


@beneficiary_bp.route("/<beneficiary_id>", methods=["GET"])
def get_beneficiary(beneficiary_id):
    """Fetches a specific beneficiary by ID."""
    db = get_db()
    beneficiary = db.beneficiaries.find_one(
        {"beneficiary_id": beneficiary_id.strip().upper()},
        {"_id": 0}
    )
    if not beneficiary:
        return jsonify({"status": "error", "message": f"Beneficiary {beneficiary_id} not found"}), 404

    return jsonify({"status": "success", "data": beneficiary}), 200


@beneficiary_bp.route("", methods=["POST"])
@token_required
def create_beneficiary():
    """Creates a new beneficiary record with input validation and authorization."""
    data = request.get_json(silent=True) or {}
    errors = validate_beneficiary_payload(data)
    if errors:
        return jsonify({"status": "error", "errors": errors, "message": errors[0]}), 400

    db = get_db()
    bid = data["beneficiary_id"].strip().upper()
    if db.beneficiaries.find_one({"beneficiary_id": bid}):
        return jsonify({"status": "error", "message": f"Beneficiary ID '{bid}' already exists"}), 409

    rc_number = (data.get("ration_card_number") or f"RC-{bid}").strip().upper()
    if db.beneficiaries.find_one({"ration_card_number": rc_number}):
        return jsonify({"status": "error", "message": f"Ration Card Number '{rc_number}' is already registered to another cardholder"}), 409

    doc = BeneficiaryModel.create_doc(
        beneficiary_id=bid,
        name=data["name"],
        region=data["region"],
        family_size=data["family_size"],
        ration_card_type=data["ration_card_type"],
        ration_card_number=rc_number,
        monthly_quota=data.get("monthly_quota")
    )
    db.beneficiaries.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"Beneficiary registered: {bid} (Region: {doc.get('region')})")

    return jsonify({
        "status": "success",
        "message": "Beneficiary registered successfully",
        "data": doc
    }), 201


@beneficiary_bp.route("/<beneficiary_id>", methods=["PUT"])
@token_required
def update_beneficiary(beneficiary_id):
    """Updates an existing beneficiary record with authorization and input validation."""
    data = request.get_json(silent=True) or {}
    bid = beneficiary_id.strip().upper()
    db = get_db()

    existing = db.beneficiaries.find_one({"beneficiary_id": bid})
    if not existing:
        return jsonify({"status": "error", "message": f"Beneficiary {bid} not found"}), 404

    update_fields = {}
    if "name" in data and data["name"]:
        name = str(data["name"]).strip()
        if len(name) < 2 or len(name) > 100:
            return jsonify({"status": "error", "message": "name must be between 2 and 100 characters"}), 400
        update_fields["name"] = name

    if "region" in data and data["region"]:
        update_fields["region"] = str(data["region"]).strip()

    if "family_size" in data:
        try:
            fsize = int(data["family_size"])
            if fsize <= 0 or fsize > 25:
                return jsonify({"status": "error", "message": "family_size must be between 1 and 25"}), 400
            update_fields["family_size"] = fsize
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "family_size must be an integer"}), 400

    if "ration_card_type" in data and data["ration_card_type"]:
        update_fields["ration_card_type"] = str(data["ration_card_type"]).strip()

    if "ration_card_number" in data and data["ration_card_number"]:
        rc_num = str(data["ration_card_number"]).strip().upper()
        conflict = db.beneficiaries.find_one({"ration_card_number": rc_num, "beneficiary_id": {"$ne": bid}})
        if conflict:
            return jsonify({"status": "error", "message": f"Ration Card Number '{rc_num}' is already in use"}), 409
        update_fields["ration_card_number"] = rc_num

    if "monthly_quota" in data and isinstance(data["monthly_quota"], dict):
        update_fields["monthly_quota"] = data["monthly_quota"]
    elif "family_size" in update_fields or "ration_card_type" in update_fields:
        # Recompute monthly quota based on updated family size and card type
        new_size = update_fields.get("family_size", existing.get("family_size", 4))
        new_type = update_fields.get("ration_card_type", existing.get("ration_card_type", "Priority (PHH)"))
        recalc_doc = BeneficiaryModel.create_doc(bid, existing.get("name", ""), existing.get("region", ""), new_size, new_type)
        update_fields["monthly_quota"] = recalc_doc["monthly_quota"]

    if "status" in data:
        update_fields["status"] = str(data["status"]).strip()

    if update_fields:
        update_fields["updated_at"] = datetime.utcnow()
        db.beneficiaries.update_one({"beneficiary_id": bid}, {"$set": update_fields})

    updated = db.beneficiaries.find_one({"beneficiary_id": bid}, {"_id": 0})
    logger.info(f"Beneficiary updated: {bid}")
    return jsonify({
        "status": "success",
        "message": "Beneficiary updated successfully",
        "data": updated
    }), 200


@beneficiary_bp.route("/<beneficiary_id>", methods=["DELETE"])
@token_required
def delete_beneficiary(beneficiary_id):
    """
    Safely deletes a beneficiary record.
    Protects audit integrity: Rejects deletion if linked distribution transactions
    or active fraud alerts exist for this cardholder.
    """
    bid = beneficiary_id.strip().upper()
    db = get_db()

    existing = db.beneficiaries.find_one({"beneficiary_id": bid})
    if not existing:
        return jsonify({"status": "error", "message": f"Beneficiary {bid} not found"}), 404

    # Protection: check related transactions history
    txn_count = db.transactions.count_documents({"beneficiary_id": bid})
    if txn_count > 0:
        return jsonify({
            "status": "error",
            "message": f"Cannot delete beneficiary '{bid}': {txn_count} distribution transaction(s) are recorded for this cardholder. Deletion blocked to protect transaction history and audit integrity."
        }), 409

    # Protection: check related fraud alerts
    alert_count = db.fraud_alerts.count_documents({"beneficiary_id": bid})
    if alert_count > 0:
        return jsonify({
            "status": "error",
            "message": f"Cannot delete beneficiary '{bid}': cardholder is associated with {alert_count} anomaly alert(s). Deletion blocked to protect audit integrity."
        }), 409

    result = db.beneficiaries.delete_one({"beneficiary_id": bid})
    if result.deleted_count == 0:
        return jsonify({"status": "error", "message": f"Beneficiary {bid} not found"}), 404

    logger.info(f"Beneficiary safely deleted: {bid}")
    return jsonify({
        "status": "success",
        "message": f"Beneficiary {bid} deleted successfully"
    }), 200
