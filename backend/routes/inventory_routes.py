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
    commodity_stock = {}
    region_stock = {}
    total_stock = 0.0
    for item in items:
        stock = float(item.get("current_stock", 0) or 0)
        commodity = item.get("commodity", "Unknown")
        region_name = item.get("region", "Unknown")
        total_stock += stock
        commodity_stock[commodity] = commodity_stock.get(commodity, 0.0) + stock
        region_stock[region_name] = region_stock.get(region_name, 0.0) + stock
    return jsonify({
        "status": "success",
        "count": len(items),
        "summary": {
            "total_stock": round(total_stock, 2),
            "commodity_stock": {key: round(value, 2) for key, value in commodity_stock.items()},
            "region_stock": {key: round(value, 2) for key, value in region_stock.items()}
        },
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
    forecasts_available = bool(alerts) and all(a.get("prediction_available", False) for a in alerts)
    total_demand = round(sum(a.get("predicted_demand") or 0.0 for a in alerts), 2) if forecasts_available else None
    total_shortage = round(sum(a.get("shortage") or 0.0 for a in alerts), 2) if forecasts_available else None
    total_procurement = round(sum(a.get("recommended_procurement") or 0.0 for a in alerts), 2) if forecasts_available else None
    shortage_count = sum(1 for a in alerts if a.get("status") == "SHORTAGE" or (a.get("shortage") or 0) > 0)
    surplus_count = sum(1 for a in alerts if a.get("status") in ("SURPLUS", "EXCESS"))
    sufficient_count = sum(1 for a in alerts if a.get("status") == "SUFFICIENT")
    total_difference = round(total_stock - (total_demand or 0.0), 2) if forecasts_available else None
    net_shortage_by_commodity = {}
    if forecasts_available:
        for item in alerts:
            commodity_name = item.get("commodity", "Unknown")
            values = net_shortage_by_commodity.setdefault(commodity_name, {"demand": 0.0, "stock": 0.0})
            values["demand"] += float(item.get("predicted_demand") or 0)
            values["stock"] += float(item.get("current_stock") or 0)
    statewide_net_shortage = (
        round(sum(max(0.0, v["demand"] - v["stock"]) for v in net_shortage_by_commodity.values()), 2)
        if forecasts_available else None
    )
    buffer_replenishment = (
        round(sum(max(0.0, float(a.get("predicted_demand") or 0) + float(a.get("buffer_stock") or 0) - float(a.get("current_stock") or 0)) for a in alerts), 2)
        if forecasts_available else None
    )

    return jsonify({
        "status": "success",
        "count": len(alerts),
        "total_stock": total_stock,
        "total_demand": total_demand,
        "total_difference": total_difference,
        "total_shortage": total_shortage,
        "depot_deficit": total_shortage,
        "statewide_net_shortage": statewide_net_shortage,
        "buffer_replenishment": buffer_replenishment,
        "total_procurement": total_procurement,
        "forecast_available": forecasts_available,
        "forecast_period": alerts[0].get("forecast_period") if alerts else None,
        "forecast_label": alerts[0].get("forecast_label") if alerts else None,
        "demand_period": "MONTHLY",
        "demand_unit": "kg/month",
        "time_horizon": "Monthly (30-day allocation cycle)",
        "shortage_count": shortage_count,
        "sufficient_count": sufficient_count,
        "surplus_count": surplus_count,
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
    """Updates stock count via thread-safe InventoryService with user identification and audit logging."""
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

    # Extract user identity for audit trail
    username = data.get("updated_by")
    auth_header = request.headers.get("Authorization", "")
    if not username and auth_header.startswith("Bearer "):
        try:
            from backend.services.auth_service import AuthService
            token_payload = AuthService.verify_token(auth_header.split(" ")[1])
            if token_payload:
                username = token_payload.get("sub")
        except Exception:
            pass
    if not username:
        username = "Administrator"

    try:
        result = InventoryService.update_stock(commodity, region, stock, user=username)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({
        "status": "success",
        "message": f"Stock level for {commodity} in {region} updated to {stock:,.1f} kg",
        "data": result if isinstance(result, dict) else {"commodity": commodity, "region": region, "current_stock": stock}
    }), 200


@inventory_bp.route("/history", methods=["GET"])
def get_inventory_history():
    """Returns recent stock adjustment audit logs."""
    db = get_db()
    query = {}
    region = request.args.get("region")
    commodity = request.args.get("commodity")
    limit = int(request.args.get("limit", 50))

    if region:
        query["region"] = region.strip()
    if commodity:
        query["commodity"] = commodity.strip()

    records = list(db.inventory_audit.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit))
    return jsonify({
        "status": "success",
        "count": len(records),
        "data": records
    }), 200
