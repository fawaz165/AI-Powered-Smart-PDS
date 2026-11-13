from flask import Blueprint, request, jsonify
import math
import re
from backend.database.mongo import get_db
from backend.models.commodity import CommodityModel
from backend.services.auth_service import role_required
from backend.utils.validators import validate_commodity_payload
from backend.utils.logger import logger

commodity_bp = Blueprint("commodities", __name__, url_prefix="/api/commodities")


def _safe_number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _enrich_commodity(record, db):
    """Enrich a Mongo record without filling missing prices or mutating stored data."""
    c = dict(record)
    code = str(c.get("commodity_code", ""))
    name = str(c.get("name", ""))
    scheme = CommodityModel.normalize_scheme_classification(
        c.get("scheme_classification"), c.get("rate_type")
    )
    v_source = c.get("verification_source") or c.get("official_source")
    is_reliable = CommodityModel.is_reliable_verification_source(v_source)
    verified = bool(c.get("is_verified") and is_reliable and scheme != "DEMO_CUSTOM")
    c["verification_source"] = v_source
    c["scheme_classification"] = scheme
    c["is_verified"] = verified
    c["is_demonstration"] = scheme == "DEMO_CUSTOM"
    c["rate_type"] = c.get("rate_type") or CommodityModel.SCHEME_TO_LEGACY[scheme]

    c["linked_inventory_count"] = db.inventory.count_documents({
        "$or": [
            {"commodity": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
            {"commodity_code": code}, {"commodity": code}
        ]
    })
    c["linked_transactions_count"] = db.transactions.count_documents({
        "$or": [
            {"commodity": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
            {"commodity_code": code}, {"commodity": code}
        ]
    })

    benchmark = _safe_number(c.get("market_price"))
    c["market_price"] = benchmark
    prices = c.get("category_pricing") if isinstance(c.get("category_pricing"), dict) else {}
    discounts = {}
    savings = {}
    category_details = {}
    for category in CommodityModel.CATEGORY_KEYS:
        issue_price = _safe_number(prices.get(category))
        is_free = (issue_price == 0.0)
        is_demo = (scheme == "DEMO_CUSTOM")
        if benchmark is not None and benchmark > 0 and issue_price is not None and issue_price >= 0 and benchmark >= issue_price:
            savings[category] = round(benchmark - issue_price, 2)
            discounts[category] = round((benchmark - issue_price) / benchmark * 100, 2)

        if issue_price is None:
            rate_status = "MISSING"
            rate_label = "Missing / Not Recorded"
        elif is_free:
            rate_status = "FREE_ENTITLEMENT"
            rate_label = "Free Entitlement (₹0.00)"
        elif is_demo:
            rate_status = "SYNTHETIC_DEMO"
            rate_label = f"Demo Rate (₹{issue_price:.2f})"
        else:
            rate_status = "ACTUAL_SUBSIDIZED"
            rate_label = f"Subsidized (₹{issue_price:.2f})"

        category_details[category] = {
            "price": issue_price,
            "is_free": is_free,
            "is_demo": is_demo,
            "rate_status": rate_status,
            "rate_label": rate_label,
            "saving": savings.get(category),
            "discount": discounts.get(category)
        }

    c["category_savings"] = savings
    c["category_discounts"] = discounts
    c["category_details"] = category_details
    c["valid_benchmark_categories"] = list(discounts)

    base_price = _safe_number(c.get("subsidized_price"))
    if base_price is not None and base_price >= 0 and benchmark is not None and benchmark > 0 and benchmark >= base_price:
        c["subsidy_amount"] = round(benchmark - base_price, 2)
        c["subsidy_percentage"] = round((benchmark - base_price) / benchmark * 100, 2)
    else:
        c["subsidy_amount"] = None
        c["subsidy_percentage"] = None
    return c


@commodity_bp.route("", methods=["GET"])
def list_commodities():
    db = get_db()
    records = list(db.commodities.find({}, {"_id": 0}).sort("commodity_code", 1))
    commodities = [_enrich_commodity(record, db) for record in records]

    discounts = [
        discount
        for commodity in commodities
        for discount in commodity["category_discounts"].values()
    ]
    verified_count = sum(1 for c in commodities if c["is_verified"])
    demo_count = sum(1 for c in commodities if c["scheme_classification"] == "DEMO_CUSTOM")
    summary = {
        "total_count": len(commodities),
        "official_count": verified_count,
        "demo_count": demo_count,
        "benchmarked_count": len(discounts),
        "average_subsidy_discount": round(sum(discounts) / len(discounts), 1) if discounts else None,
        "averaging_method": "arithmetic_mean_of_valid_category_issue_prices_vs_recorded_benchmarks",
    }
    return jsonify({"status": "success", "count": len(commodities), "data": commodities, "summary": summary}), 200


@commodity_bp.route("/<commodity_code>", methods=["GET"])
def get_commodity(commodity_code):
    db = get_db()
    code = commodity_code.strip().upper()
    record = db.commodities.find_one({"commodity_code": code})
    if not record:
        record = db.commodities.find_one({"name": {"$regex": f"^{re.escape(commodity_code)}$", "$options": "i"}})
    if not record:
        return jsonify({"status": "error", "message": f"Commodity '{commodity_code}' not found"}), 404
    record.pop("_id", None)
    return jsonify({"status": "success", "data": _enrich_commodity(record, db)}), 200


@commodity_bp.route("", methods=["POST"])
@role_required("admin")
def create_commodity():
    data = request.get_json(silent=True) or {}
    errors = validate_commodity_payload(data)
    if errors:
        return jsonify({"status": "error", "errors": errors, "message": errors[0]}), 400

    code = data["commodity_code"].strip().upper()
    name = data["name"].strip()
    db = get_db()
    if db.commodities.find_one({"commodity_code": code}):
        return jsonify({"status": "error", "message": f"Commodity code '{code}' already exists"}), 409
    if db.commodities.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}):
        return jsonify({"status": "error", "message": f"Commodity name '{name}' already exists"}), 409

    legacy_rate = data.get("rate_type")
    scheme = CommodityModel.normalize_scheme_classification(data.get("scheme_classification"), legacy_rate)
    doc = CommodityModel.create_doc(
        commodity_code=code, name=name, unit=data.get("unit", "kg"),
        subsidized_price=data.get("subsidized_price"), market_price=data.get("market_price"),
        rate_type=legacy_rate, scheme_classification=scheme,
        category_pricing=data.get("category_pricing"), description=data.get("description"),
        official_source=data.get("official_source"), verification_source=data.get("verification_source"),
        is_verified=False,
    )
    db.commodities.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"Commodity created: {code} ({name})")
    return jsonify({"status": "success", "message": f"Commodity '{name}' registered successfully", "data": _enrich_commodity(doc, db)}), 201


@commodity_bp.route("/<commodity_code>", methods=["PUT"])
@role_required("admin")
def update_commodity(commodity_code):
    data = request.get_json(silent=True) or {}
    code = commodity_code.strip().upper()
    db = get_db()
    existing = db.commodities.find_one({"commodity_code": code})
    if not existing:
        return jsonify({"status": "error", "message": f"Commodity '{code}' not found"}), 404

    validation_data = {"commodity_code": code, "name": data.get("name", existing.get("name", "")),
                       "unit": data.get("unit", existing.get("unit", "kg"))}
    validation_data["scheme_classification"] = existing.get("scheme_classification") or CommodityModel.normalize_scheme_classification(None, existing.get("rate_type"))
    validation_data["rate_type"] = existing.get("rate_type") or CommodityModel.SCHEME_TO_LEGACY[validation_data["scheme_classification"]]
    for key in ("subsidized_price", "market_price", "category_pricing", "scheme_classification", "rate_type"):
        if key in data:
            validation_data[key] = data[key]
        elif key in ("category_pricing", "market_price", "subsidized_price"):
            validation_data[key] = existing.get(key)
    # A legacy generic-price update means the same issue price for every
    # category; validate it as such instead of against stale category rates.
    if "subsidized_price" in data and "category_pricing" not in data:
        validation_data.pop("category_pricing", None)
    errors = validate_commodity_payload(validation_data)
    if errors:
        return jsonify({"status": "error", "errors": errors, "message": errors[0]}), 400

    update_fields = {}
    if "name" in data:
        new_name = data["name"].strip()
        conflict = db.commodities.find_one({"name": {"$regex": f"^{re.escape(new_name)}$", "$options": "i"}, "commodity_code": {"$ne": code}})
        if conflict:
            return jsonify({"status": "error", "message": f"Commodity name '{new_name}' is already used"}), 409
        update_fields["name"] = new_name
    if "unit" in data:
        update_fields["unit"] = data["unit"].strip().lower()
    if "description" in data:
        update_fields["description"] = data["description"].strip()
    if "category_pricing" in data:
        prices = {k: float(data["category_pricing"][k]) for k in CommodityModel.CATEGORY_KEYS}
        update_fields["category_pricing"] = prices
        update_fields["subsidized_price"] = data.get("subsidized_price", min(prices.values()))
    if "subsidized_price" in data:
        update_fields["subsidized_price"] = float(data["subsidized_price"])
        if "category_pricing" not in data:
            generic_price = float(data["subsidized_price"])
            update_fields["category_pricing"] = {key: generic_price for key in CommodityModel.CATEGORY_KEYS}
    if "market_price" in data:
        update_fields["market_price"] = _safe_number(data["market_price"])
    if "scheme_classification" in data or "rate_type" in data:
        scheme = CommodityModel.normalize_scheme_classification(
            data.get("scheme_classification"), data.get("rate_type")
        )
        update_fields["scheme_classification"] = scheme
        update_fields["rate_type"] = CommodityModel.SCHEME_TO_LEGACY[scheme]
        update_fields["is_demonstration"] = scheme == "DEMO_CUSTOM"
        update_fields["is_verified"] = False
    if "category_pricing" in data or "subsidized_price" in data or "scheme_classification" in data or "rate_type" in data:
        update_fields["is_verified"] = False
        update_fields["verification_source"] = None
    if "official_source" in data:
        update_fields["official_source"] = str(data["official_source"] or "").strip() or None

    if update_fields:
        db.commodities.update_one({"commodity_code": code}, {"$set": update_fields})
    updated = db.commodities.find_one({"commodity_code": code})
    updated.pop("_id", None)
    return jsonify({"status": "success", "message": f"Commodity '{code}' updated successfully", "data": _enrich_commodity(updated, db)}), 200


@commodity_bp.route("/<commodity_code>", methods=["DELETE"])
@role_required("admin")
def delete_commodity(commodity_code):
    code = commodity_code.strip().upper()
    db = get_db()
    existing = db.commodities.find_one({"commodity_code": code})
    if not existing:
        return jsonify({"status": "error", "message": f"Commodity '{code}' not found"}), 404

    name = existing.get("name", "")
    links = {"$or": [
        {"commodity": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"commodity_code": code}, {"commodity": code}
    ]}
    inventory_count = db.inventory.count_documents(links)
    transaction_count = db.transactions.count_documents(links)
    if inventory_count or transaction_count:
        return jsonify({"status": "error", "message": f"Cannot delete commodity '{code}': linked to {inventory_count} inventory record(s) and {transaction_count} transaction(s)."}), 409
    result = db.commodities.delete_one({"commodity_code": code})
    if result.deleted_count != 1:
        return jsonify({"status": "error", "message": f"Commodity '{code}' not found"}), 404
    return jsonify({"status": "success", "message": f"Commodity '{code}' deleted successfully"}), 200
