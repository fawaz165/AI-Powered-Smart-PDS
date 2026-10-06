from flask import Blueprint, request, jsonify
from datetime import datetime
from backend.database.mongo import get_db
from backend.services.inventory_service import InventoryService
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
    """
    alerts = InventoryService.calculate_inventory_alerts()
    return jsonify({
        "status": "success",
        "count": len(alerts),
        "data": alerts
    }), 200


@inventory_bp.route("", methods=["POST"])
def add_inventory():
    """Adds a new commodity/region inventory record or adjusts existing."""
    data = request.get_json(silent=True) or {}
    errors = validate_inventory_payload(data)
    if errors:
        return jsonify({"status": "error", "errors": errors}), 400

    commodity = data["commodity"].strip()
    region = data["region"].strip()
    stock = float(data["current_stock"])
    buffer_stock = float(data.get("buffer_stock", 500.0))
    unit = data.get("unit", "kg")

    db = get_db()
    db.inventory.update_one(
        {"commodity": commodity, "region": region},
        {"$set": {
            "commodity": commodity,
            "region": region,
            "current_stock": stock,
            "buffer_stock": buffer_stock,
            "unit": unit,
            "last_updated": datetime.utcnow()
        }},
        upsert=True
    )
    logger.info(f"Inventory set: {commodity} ({region}) = {stock} {unit}")
    return jsonify({
        "status": "success",
        "message": f"Inventory updated for {commodity} in {region}",
        "data": {
            "commodity": commodity,
            "region": region,
            "current_stock": stock,
            "buffer_stock": buffer_stock,
            "unit": unit
        }
    }), 201


@inventory_bp.route("/update-stock", methods=["PUT"])
def update_stock_level():
    """Updates stock count via thread-safe InventoryService."""
    data = request.get_json(silent=True) or {}
    commodity = data.get("commodity")
    region = data.get("region")
    stock = data.get("current_stock")

    if not commodity or not region or stock is None:
        return jsonify({"status": "error", "message": "commodity, region, and current_stock are required"}), 400

    try:
        stock = float(stock)
        if stock < 0:
            return jsonify({"status": "error", "message": "current_stock cannot be negative"}), 400
    except ValueError:
        return jsonify({"status": "error", "message": "current_stock must be numeric"}), 400

    InventoryService.update_stock(commodity, region, stock)
    return jsonify({
        "status": "success",
        "message": f"Stock level updated to {stock} kg",
        "data": {"commodity": commodity, "region": region, "current_stock": stock}
    }), 200
