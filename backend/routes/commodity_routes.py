from flask import Blueprint, request, jsonify
import re
from backend.database.mongo import get_db
from backend.models.commodity import CommodityModel
from backend.services.auth_service import token_required
from backend.utils.validators import validate_commodity_payload
from backend.utils.logger import logger

commodity_bp = Blueprint("commodities", __name__, url_prefix="/api/commodities")


@commodity_bp.route("", methods=["GET"])
def list_commodities():
    """Lists all registered commodities enriched with linked inventory and transaction counts."""
    db = get_db()
    commodities = list(db.commodities.find({}, {"_id": 0}).sort("commodity_code", 1))

    # Enrich each commodity with operational linkage statistics
    for c in commodities:
        cname = c.get("name", "")
        ccode = c.get("commodity_code", "")
        c["linked_inventory_count"] = db.inventory.count_documents({
            "$or": [
                {"commodity": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}},
                {"commodity_code": ccode}
            ]
        })
        c["linked_transactions_count"] = db.transactions.count_documents({
            "$or": [
                {"commodity": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}},
                {"commodity_code": ccode}
            ]
        })
        if "rate_type" not in c:
            c["rate_type"] = "OFFICIAL_NFSA" if c.get("commodity_code") in ["COM-RIC", "COM-WHT", "COM-SUG"] else "DEMONSTRATION"
        if "is_demonstration" not in c:
            c["is_demonstration"] = (c.get("rate_type") == "DEMONSTRATION")

    return jsonify({
        "status": "success",
        "count": len(commodities),
        "data": commodities
    }), 200


@commodity_bp.route("/<commodity_code>", methods=["GET"])
def get_commodity(commodity_code):
    """Fetches details of a specific commodity by code or name."""
    db = get_db()
    code = commodity_code.strip().upper()
    com = db.commodities.find_one({"commodity_code": code}, {"_id": 0})
    if not com:
        # Also check by name
        com = db.commodities.find_one({"name": {"$regex": f"^{re.escape(commodity_code)}$", "$options": "i"}}, {"_id": 0})
    if not com:
        return jsonify({"status": "error", "message": f"Commodity '{commodity_code}' not found"}), 404

    cname = com.get("name", "")
    ccode = com.get("commodity_code", code)
    com["linked_inventory_count"] = db.inventory.count_documents({
        "$or": [
            {"commodity": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}},
            {"commodity_code": ccode}
        ]
    })
    com["linked_transactions_count"] = db.transactions.count_documents({
        "$or": [
            {"commodity": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}},
            {"commodity_code": ccode}
        ]
    })

    return jsonify({"status": "success", "data": com}), 200


@commodity_bp.route("", methods=["POST"])
@token_required
def create_commodity():
    """Registers a new commodity with validation, duplicate checks, and configurable pricing."""
    data = request.get_json(silent=True) or {}
    errors = validate_commodity_payload(data)
    if errors:
        return jsonify({"status": "error", "errors": errors, "message": errors[0]}), 400

    code = data["commodity_code"].strip().upper()
    name = data["name"].strip()
    db = get_db()

    # Duplicate code prevention
    if db.commodities.find_one({"commodity_code": code}):
        return jsonify({"status": "error", "message": f"Commodity code '{code}' already exists"}), 409

    # Duplicate name prevention
    if db.commodities.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}):
        return jsonify({"status": "error", "message": f"Commodity name '{name}' already exists"}), 409

    doc = CommodityModel.create_doc(
        commodity_code=code,
        name=name,
        unit=data.get("unit", "kg"),
        subsidized_price=data.get("subsidized_price", 0.0),
        market_price=data.get("market_price"),
        rate_type=data.get("rate_type", "OFFICIAL_NFSA"),
        description=data.get("description")
    )
    db.commodities.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"Commodity created: {code} ({name}) - Price: ₹{doc['subsidized_price']}")

    return jsonify({
        "status": "success",
        "message": f"Commodity '{name}' registered successfully",
        "data": doc
    }), 201


@commodity_bp.route("/<commodity_code>", methods=["PUT"])
@token_required
def update_commodity(commodity_code):
    """Updates commodity pricing, classification, or details."""
    data = request.get_json(silent=True) or {}
    code = commodity_code.strip().upper()
    db = get_db()

    existing = db.commodities.find_one({"commodity_code": code})
    if not existing:
        return jsonify({"status": "error", "message": f"Commodity '{code}' not found"}), 404

    update_fields = {}
    if "name" in data and data["name"]:
        new_name = data["name"].strip()
        conflict = db.commodities.find_one({"name": {"$regex": f"^{re.escape(new_name)}$", "$options": "i"}, "commodity_code": {"$ne": code}})
        if conflict:
            return jsonify({"status": "error", "message": f"Commodity name '{new_name}' is already used by another commodity"}), 409
        update_fields["name"] = new_name

    if "subsidized_price" in data:
        try:
            s_price = float(data["subsidized_price"])
            if s_price < 0:
                return jsonify({"status": "error", "message": "subsidized_price cannot be negative"}), 400
            update_fields["subsidized_price"] = s_price
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "subsidized_price must be numeric"}), 400

    if "market_price" in data and data["market_price"] is not None:
        try:
            m_price = float(data["market_price"])
            if m_price < 0:
                return jsonify({"status": "error", "message": "market_price cannot be negative"}), 400
            update_fields["market_price"] = m_price
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "market_price must be numeric"}), 400

    if "rate_type" in data and data["rate_type"]:
        rtype = str(data["rate_type"]).strip().upper()
        if rtype in CommodityModel.VALID_RATE_TYPES:
            update_fields["rate_type"] = rtype
            update_fields["is_demonstration"] = (rtype == "DEMONSTRATION")

    if "description" in data:
        update_fields["description"] = data["description"].strip()
    if "unit" in data and data["unit"]:
        update_fields["unit"] = data["unit"].strip().lower()

    if update_fields:
        db.commodities.update_one({"commodity_code": code}, {"$set": update_fields})

    updated = db.commodities.find_one({"commodity_code": code}, {"_id": 0})
    logger.info(f"Commodity updated: {code}")
    return jsonify({
        "status": "success",
        "message": f"Commodity '{code}' updated successfully",
        "data": updated
    }), 200


@commodity_bp.route("/<commodity_code>", methods=["DELETE"])
@token_required
def delete_commodity(commodity_code):
    """
    Safely deletes a commodity.
    Blocks deletion if the commodity is linked to active inventory or transactions.
    """
    code = commodity_code.strip().upper()
    db = get_db()
    existing = db.commodities.find_one({"commodity_code": code})
    if not existing:
        return jsonify({"status": "error", "message": f"Commodity '{code}' not found"}), 404

    cname = existing.get("name", "")
    ccode = existing.get("commodity_code", code)
    inv_count = db.inventory.count_documents({
        "$or": [
            {"commodity": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}},
            {"commodity_code": ccode}
        ]
    })
    txn_count = db.transactions.count_documents({
        "$or": [
            {"commodity": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}},
            {"commodity_code": ccode}
        ]
    })

    if inv_count > 0 or txn_count > 0:
        return jsonify({
            "status": "error",
            "message": f"Cannot delete commodity '{code}' ({cname}): linked to {inv_count} regional inventory record(s) and {txn_count} distribution transaction(s). Deletion blocked to preserve operational integrity."
        }), 409

    result = db.commodities.delete_one({"commodity_code": code})
    if result.deleted_count == 0:
        return jsonify({"status": "error", "message": f"Commodity '{code}' not found"}), 404

    logger.info(f"Commodity safely deleted: {code}")
    return jsonify({
        "status": "success",
        "message": f"Commodity '{code}' deleted successfully"
    }), 200
