from flask import Blueprint, request, jsonify
from backend.database.mongo import get_db
from backend.models.commodity import CommodityModel
from backend.utils.validators import validate_commodity_payload
from backend.utils.logger import logger

commodity_bp = Blueprint("commodities", __name__, url_prefix="/api/commodities")


@commodity_bp.route("", methods=["GET"])
def list_commodities():
    """Lists all registered commodities."""
    db = get_db()
    commodities = list(db.commodities.find({}, {"_id": 0}))
    return jsonify({
        "status": "success",
        "count": len(commodities),
        "data": commodities
    }), 200


@commodity_bp.route("/<commodity_code>", methods=["GET"])
def get_commodity(commodity_code):
    """Fetches details of a specific commodity."""
    db = get_db()
    code = commodity_code.strip().upper()
    com = db.commodities.find_one({"commodity_code": code}, {"_id": 0})
    if not com:
        # Also check by name
        com = db.commodities.find_one({"name": {"$regex": f"^{commodity_code}$", "$options": "i"}}, {"_id": 0})
    if not com:
        return jsonify({"status": "error", "message": f"Commodity '{commodity_code}' not found"}), 404

    return jsonify({"status": "success", "data": com}), 200


@commodity_bp.route("", methods=["POST"])
def create_commodity():
    """Registers a new commodity."""
    data = request.get_json(silent=True) or {}
    errors = validate_commodity_payload(data)
    if errors:
        return jsonify({"status": "error", "errors": errors}), 400

    code = data["commodity_code"].strip().upper()
    name = data["name"].strip()
    db = get_db()

    if db.commodities.find_one({"$or": [{"commodity_code": code}, {"name": name}]}):
        return jsonify({"status": "error", "message": f"Commodity with code '{code}' or name '{name}' already exists"}), 409

    doc = CommodityModel.create_doc(
        commodity_code=code,
        name=name,
        unit=data.get("unit", "kg"),
        subsidized_price=data.get("subsidized_price", 0.0),
        description=data.get("description")
    )
    db.commodities.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"Commodity created: {code} ({name})")

    return jsonify({
        "status": "success",
        "message": "Commodity registered successfully",
        "data": doc
    }), 201


@commodity_bp.route("/<commodity_code>", methods=["PUT"])
def update_commodity(commodity_code):
    """Updates commodity pricing or details."""
    data = request.get_json(silent=True) or {}
    code = commodity_code.strip().upper()
    db = get_db()

    existing = db.commodities.find_one({"commodity_code": code})
    if not existing:
        return jsonify({"status": "error", "message": f"Commodity '{code}' not found"}), 404

    update_fields = {}
    if "name" in data:
        update_fields["name"] = data["name"].strip()
    if "subsidized_price" in data:
        try:
            update_fields["subsidized_price"] = float(data["subsidized_price"])
        except ValueError:
            return jsonify({"status": "error", "message": "subsidized_price must be numeric"}), 400
    if "description" in data:
        update_fields["description"] = data["description"].strip()
    if "unit" in data:
        update_fields["unit"] = data["unit"].strip().lower()

    if update_fields:
        db.commodities.update_one({"commodity_code": code}, {"$set": update_fields})

    updated = db.commodities.find_one({"commodity_code": code}, {"_id": 0})
    logger.info(f"Commodity updated: {code}")
    return jsonify({
        "status": "success",
        "message": "Commodity updated successfully",
        "data": updated
    }), 200


@commodity_bp.route("/<commodity_code>", methods=["DELETE"])
def delete_commodity(commodity_code):
    """Deletes a commodity."""
    code = commodity_code.strip().upper()
    db = get_db()
    result = db.commodities.delete_one({"commodity_code": code})
    if result.deleted_count == 0:
        return jsonify({"status": "error", "message": f"Commodity '{code}' not found"}), 404

    logger.info(f"Commodity deleted: {code}")
    return jsonify({
        "status": "success",
        "message": f"Commodity '{code}' deleted successfully"
    }), 200
