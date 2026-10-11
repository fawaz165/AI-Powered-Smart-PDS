import re


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

    if "unit" in data and data["unit"]:
        unit = str(data["unit"]).strip().lower()
        if len(unit) > 15:
            errors.append("Measurement unit must be under 15 characters")

    if "subsidized_price" in data:
        try:
            price = float(data["subsidized_price"])
            if price < 0:
                errors.append("subsidized_price cannot be negative")
        except (ValueError, TypeError):
            errors.append("subsidized_price must be a valid numeric value")

    if "market_price" in data and data["market_price"] is not None:
        try:
            mprice = float(data["market_price"])
            if mprice < 0:
                errors.append("market_price cannot be negative")
        except (ValueError, TypeError):
            errors.append("market_price must be a valid numeric value")

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
