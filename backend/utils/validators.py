import re
import math


def validate_beneficiary_payload(data):
    """Validates incoming beneficiary creation payload."""
    errors = []
    if not data or not isinstance(data, dict):
        return ["Request body must be a valid JSON object"]

    bid = str(data.get("beneficiary_id", "")).strip()
    if not bid:
        errors.append("beneficiary_id is required")
    elif len(bid) < 3 or len(bid) > 30:
        errors.append("beneficiary_id must be between 3 and 30 characters")
    elif not re.match(r"^[A-Za-z0-9\-_]+$", bid):
        errors.append("beneficiary_id may only contain alphanumeric characters, hyphens, and underscores")

    name = str(data.get("name", "")).strip()
    if not name:
        errors.append("name is required")
    elif len(name) < 2 or len(name) > 100:
        errors.append("name must be between 2 and 100 characters")

    region = str(data.get("region", "")).strip()
    if not region:
        errors.append("region is required")
    elif len(region) < 2 or len(region) > 50:
        errors.append("region must be between 2 and 50 characters")

    try:
        family_size = int(data.get("family_size", 0))
        if family_size <= 0 or family_size > 25:
            errors.append("family_size must be a positive integer between 1 and 25")
    except (ValueError, TypeError):
        errors.append("family_size must be a valid integer between 1 and 25")

    card_type = str(data.get("ration_card_type", "")).strip()
    valid_card_types = [
        "Priority (PHH)",
        "Antyodaya Anna Yojana (AAY)",
        "Non-Priority (NPHH)"
    ]
    if not card_type:
        errors.append("ration_card_type is required")
    elif not any(vt.lower() in card_type.lower() or card_type.lower() in vt.lower() for vt in valid_card_types):
        errors.append(f"ration_card_type must be one of: {', '.join(valid_card_types)}")

    rc_num = str(data.get("ration_card_number", "")).strip()
    if rc_num and not re.match(r"^[A-Za-z0-9\-_]{3,35}$", rc_num):
        errors.append("ration_card_number must be 3-35 characters containing only letters, numbers, hyphens, or underscores")

    quota = data.get("monthly_quota")
    if quota is not None:
        if not isinstance(quota, dict):
            errors.append("monthly_quota must be a valid dictionary of commodities and quantities")
        else:
            for comm, qty in quota.items():
                try:
                    if float(qty) < 0:
                        errors.append(f"monthly_quota for {comm} cannot be negative")
                except (ValueError, TypeError):
                    errors.append(f"monthly_quota for {comm} must be numeric")

    return errors


def validate_commodity_payload(data):
    """Validates incoming commodity registration and update payload."""
    errors = []
    if not data or not isinstance(data, dict):
        return ["Request body must be a valid JSON object"]

    code = str(data.get("commodity_code", "")).strip().upper()
    if not code:
        errors.append("commodity_code is required")
    elif len(code) < 3 or len(code) > 20:
        errors.append("commodity_code must be between 3 and 20 characters")
    elif not re.match(r"^[A-Za-z0-9\-_]+$", code):
        errors.append("commodity_code may only contain alphanumeric characters, hyphens, and underscores")

    name = str(data.get("name", "")).strip()
    if not name:
        errors.append("Commodity name is required")
    elif len(name) < 2 or len(name) > 50:
        errors.append("Commodity name must be between 2 and 50 characters")
    elif not re.match(r"^[A-Za-z][A-Za-z0-9\s\-_()]{1,49}$", name):
        errors.append("Commodity name must start with a letter and contain only alphanumeric characters, spaces, hyphens, and parentheses")

    if "unit" not in data or not str(data.get("unit", "")).strip():
        errors.append("unit is required")
    else:
        unit = str(data["unit"]).strip().lower()
        if len(unit) > 15:
            errors.append("Measurement unit must be under 15 characters")

    parsed_sub_price = None
    if "category_pricing" not in data and data.get("subsidized_price") in (None, ""):
        errors.append("category_pricing or subsidized_price is required")
    if "subsidized_price" in data and data["subsidized_price"] not in (None, ""):
        try:
            parsed_sub_price = float(data["subsidized_price"])
            if parsed_sub_price < 0:
                errors.append("subsidized_price cannot be negative")
        except (ValueError, TypeError):
            errors.append("subsidized_price must be a valid numeric value")

    parsed_market_price = None
    if "market_price" in data and data["market_price"] is not None and data["market_price"] != "":
        try:
            parsed_market_price = float(data["market_price"])
            if not math.isfinite(parsed_market_price) or parsed_market_price < 0:
                errors.append("market_price cannot be negative")
        except (ValueError, TypeError):
            errors.append("market_price must be a valid numeric value")

    category_prices = data.get("category_pricing")
    parsed_category_prices = {}
    if category_prices is not None:
        if not isinstance(category_prices, dict):
            errors.append("category_pricing must be an object with AAY, PHH and NPHH prices")
        else:
            for category in ("AAY", "PHH", "NPHH"):
                if category not in category_prices:
                    errors.append(f"category_pricing.{category} is required")
                    continue
                try:
                    price = float(category_prices[category])
                    if not math.isfinite(price) or price < 0:
                        errors.append(f"category_pricing.{category} must be a finite non-negative price")
                    else:
                        parsed_category_prices[category] = price
                except (ValueError, TypeError):
                    errors.append(f"category_pricing.{category} must be numeric")

    if parsed_market_price is not None:
        prices_to_compare = list(parsed_category_prices.values()) or ([parsed_sub_price] if parsed_sub_price is not None else [])
        if any(parsed_market_price < price for price in prices_to_compare):
            errors.append("market_price cannot be less than an issue price")

    classification = str(data.get("scheme_classification", "")).strip().upper()
    if not classification and not data.get("rate_type"):
        errors.append("scheme_classification is required")
    if classification and classification not in ["NFSA", "TAMIL_NADU_STATE_PDS", "DEMO_CUSTOM"]:
        errors.append("scheme_classification must be NFSA, TAMIL_NADU_STATE_PDS, or DEMO_CUSTOM")

    if "rate_type" in data and data["rate_type"]:
        rate_type = str(data["rate_type"]).strip().upper()
        if rate_type not in ["OFFICIAL_NFSA", "DEMONSTRATION", "STATE_SUBSIDY"]:
            errors.append("rate_type must be one of: OFFICIAL_NFSA, DEMONSTRATION, STATE_SUBSIDY")

    return errors


def validate_inventory_payload(data):
    """Validates inventory payload."""
    errors = []
    if not data or not isinstance(data, dict):
        return ["Request body must be a valid JSON object"]
    if not data.get("commodity") and not data.get("commodity_code"):
        errors.append("commodity or commodity_code is required")
    if not data.get("region"):
        errors.append("region is required")
    try:
        stock = float(data.get("current_stock", 0))
        if stock < 0:
            errors.append("current_stock cannot be negative")
    except (ValueError, TypeError):
        errors.append("current_stock must be a valid numeric value")
    if "buffer_stock" in data and data["buffer_stock"] is not None:
        try:
            buf = float(data["buffer_stock"])
            if buf < 0:
                errors.append("buffer_stock cannot be negative")
        except (ValueError, TypeError):
            errors.append("buffer_stock must be a valid numeric value")
    return errors


def validate_transaction_payload(data):
    """Validates distribution transaction payload."""
    errors = []
    if not data or not isinstance(data, dict):
        return ["Request body must be a valid JSON object"]
    if not data.get("beneficiary_id"):
        errors.append("beneficiary_id is required")
    if not data.get("commodity") and not data.get("commodity_code"):
        errors.append("commodity or commodity_code is required")
    try:
        qty = float(data.get("quantity", 0))
        if qty <= 0:
            errors.append("quantity must be greater than zero")
    except (ValueError, TypeError):
        errors.append("quantity must be a valid number")
    return errors
