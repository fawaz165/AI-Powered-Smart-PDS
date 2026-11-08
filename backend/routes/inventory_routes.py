from flask import Blueprint, request, jsonify
from datetime import datetime
from backend.database.mongo import get_db
from backend.services.inventory_service import InventoryService
from backend.services.auth_service import token_required, role_required
from backend.utils.validators import validate_inventory_payload
from backend.utils.logger import logger

inventory_bp = Blueprint("inventory", __name__, url_prefix="/api/inventory")


@inventory_bp.route("", methods=["GET"])
def list_inventory():
    """Lists inventory across all commodities and regions."""
    db = get_db()
    query = {}
    region = request.args.get("region")
    commodity = request.args.get("commodity")

    if region:
        query["region"] = region
    if commodity:
        query["commodity"] = commodity

    items = list(db.inventory.find(query, {"_id": 0}))
    return jsonify({
        "status": "success",
        "count": len(items),
        "data": items
    }), 200


@inventory_bp.route("/alerts", methods=["GET"])
def get_inventory_alerts():
    """
    Computes intelligent inventory alerts, compares current stock with predicted demand,
    and returns shortage and recommended procurement figures.
    Supports optional region, commodity, and include_safety_stock filters.
    """
    include_safety = request.args.get("include_safety_stock", "false").lower() in ("true", "1", "yes")
    region = (request.args.get("region") or "").strip() or None
    commodity = (request.args.get("commodity") or "").strip() or None

    alerts = InventoryService.calculate_inventory_alerts(
        include_safety_stock=include_safety,
        region=region,
        commodity=commodity
    )

    total_stock = round(sum(a.get("current_stock", 0.0) for a in alerts), 2)
    total_demand = round(sum(a.get("predicted_demand", 0.0) for a in alerts), 2)
    total_shortage = round(sum(a.get("shortage", 0.0) for a in alerts), 2)
    total_procurement = round(sum(a.get("recommended_procurement", 0.0) for a in alerts), 2)
    shortage_count = sum(1 for a in alerts if a.get("shortage", 0.0) > 0 or a.get("status") == "SHORTAGE")
    sufficient_count = len(alerts) - shortage_count

    return jsonify({
        "status": "success",
        "count": len(alerts),
        "total_stock": total_stock,
        "total_demand": total_demand,
        "total_shortage": total_shortage,
        "total_procurement": total_procurement,
        "shortage_count": shortage_count,
        "sufficient_count": sufficient_count,
        "safety_stock_included": include_safety,
        "data": alerts
    }), 200


@inventory_bp.route("", methods=["POST"])
@role_required("admin", "officer")
def add_inventory():
    """Adds a new commodity/region inventory record or adjusts existing."""
    data = request.get_json(silent=True) or {}
    errors = validate_inventory_payload(data)
    if errors:
        return jsonify({"status": "error", "errors": errors}), 400

    commodity = (data.get("commodity") or data.get("commodity_code", "")).strip()
    region = data["region"].strip()
    stock = float(data["current_stock"])
    buffer_stock = float(data.get("buffer_stock", 500.0))
    unit = data.get("unit", "kg")
    commodity_code = data.get("commodity_code")

    doc = InventoryModel.create_doc(
        commodity=commodity,
        region=region,
        current_stock=stock,
        unit=unit,
        buffer_stock=buffer_stock,
        commodity_code=commodity_code
    )

    db = get_db()
    db.inventory.update_one(
        {
            "$or": [
                {"commodity": doc["commodity"]},
                {"commodity_code": doc["commodity_code"]}
            ],
            "region": region
        },
        {"$set": doc},
        upsert=True
    )
    logger.info(f"Inventory set: {doc['commodity']} ({doc['commodity_code']} in {region}) = {stock} {unit}")
    return jsonify({
        "status": "success",
        "message": f"Inventory updated for {doc['commodity']} in {region}",
        "data": doc
    }), 201


@inventory_bp.route("/update-stock", methods=["PUT"])
def update_stock_level():
    """Updates stock count via thread-safe InventoryService."""
    data = request.get_json(silent=True) or {}
    commodity = (data.get("commodity") or data.get("commodity_code", "")).strip()
    region = (data.get("region") or "").strip()
    stock = data.get("current_stock")

    if not commodity or not region or stock is None:
        return jsonify({"status": "error", "message": "commodity (or commodity_code), region, and current_stock are required"}), 400

    try:
        stock = float(stock)
        if stock < 0:
            return jsonify({"status": "error", "message": "current_stock cannot be negative"}), 400
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "current_stock must be a valid non-negative number"}), 400

    try:
        InventoryService.update_stock(commodity, region, stock)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({
        "status": "success",
        "message": f"Stock level updated to {stock:,.1f} kg",
        "data": {"commodity": commodity, "region": region, "current_stock": stock}
    }), 200
