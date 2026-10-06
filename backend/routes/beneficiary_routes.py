from flask import Blueprint, request, jsonify
from datetime import datetime
from backend.database.mongo import get_db
from backend.models.beneficiary import BeneficiaryModel
from backend.utils.validators import validate_beneficiary_payload
from backend.utils.logger import logger

beneficiary_bp = Blueprint("beneficiaries", __name__, url_prefix="/api/beneficiaries")


@beneficiary_bp.route("", methods=["GET"])
def list_beneficiaries():
    """Lists all beneficiaries with optional filtering by region and card type."""
    db = get_db()
    query = {}
    region = request.args.get("region")
    card_type = request.args.get("ration_card_type")
    search = request.args.get("search")

    if region:
        query["region"] = region
    if card_type:
        query["ration_card_type"] = card_type
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"beneficiary_id": {"$regex": search, "$options": "i"}},
            {"ration_card_number": {"$regex": search, "$options": "i"}}
        ]

    limit = int(request.args.get("limit", 100))
    skip = int(request.args.get("skip", 0))

    cursor = db.beneficiaries.find(query, {"_id": 0}).skip(skip).limit(limit)
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
def create_beneficiary():
    """Creates a new beneficiary record."""
    data = request.get_json(silent=True) or {}
    errors = validate_beneficiary_payload(data)
    if errors:
        return jsonify({"status": "error", "errors": errors}), 400

    db = get_db()
    bid = data["beneficiary_id"].strip().upper()
    if db.beneficiaries.find_one({"beneficiary_id": bid}):
        return jsonify({"status": "error", "message": f"Beneficiary ID '{bid}' already exists"}), 409

    doc = BeneficiaryModel.create_doc(
        beneficiary_id=bid,
        name=data["name"],
        region=data["region"],
        family_size=data["family_size"],
        ration_card_type=data["ration_card_type"],
        ration_card_number=data.get("ration_card_number"),
        monthly_quota=data.get("monthly_quota")
    )
    db.beneficiaries.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"Beneficiary created: {bid}")

    return jsonify({
        "status": "success",
        "message": "Beneficiary created successfully",
        "data": doc
    }), 201


@beneficiary_bp.route("/<beneficiary_id>", methods=["PUT"])
def update_beneficiary(beneficiary_id):
    """Updates an existing beneficiary record."""
    data = request.get_json(silent=True) or {}
    bid = beneficiary_id.strip().upper()
    db = get_db()

    existing = db.beneficiaries.find_one({"beneficiary_id": bid})
    if not existing:
        return jsonify({"status": "error", "message": f"Beneficiary {bid} not found"}), 404

    update_fields = {}
    if "name" in data and data["name"]:
        update_fields["name"] = data["name"].strip()
    if "region" in data and data["region"]:
        update_fields["region"] = data["region"].strip()
    if "family_size" in data:
        try:
            update_fields["family_size"] = int(data["family_size"])
        except ValueError:
            return jsonify({"status": "error", "message": "family_size must be an integer"}), 400
    if "ration_card_type" in data and data["ration_card_type"]:
        update_fields["ration_card_type"] = data["ration_card_type"].strip()
    if "status" in data:
        update_fields["status"] = data["status"]

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
def delete_beneficiary(beneficiary_id):
    """Deletes a beneficiary record."""
    bid = beneficiary_id.strip().upper()
    db = get_db()
    result = db.beneficiaries.delete_one({"beneficiary_id": bid})
    if result.deleted_count == 0:
        return jsonify({"status": "error", "message": f"Beneficiary {bid} not found"}), 404

    logger.info(f"Beneficiary deleted: {bid}")
    return jsonify({
        "status": "success",
        "message": f"Beneficiary {bid} deleted successfully"
    }), 200
