import re


def validate_beneficiary_payload(data):
    """Validates incoming beneficiary creation/update payload."""
    errors = []
    if not data or not isinstance(data, dict):
        return ["Request body must be a valid JSON object"]

    if not data.get("beneficiary_id") or not str(data["beneficiary_id"]).strip():
        errors.append("beneficiary_id is required")
    if not data.get("name") or not str(data["name"]).strip():
        errors.append("name is required")
    if not data.get("region") or not str(data["region"]).strip():
        errors.append("region is required")

    try:
        family_size = int(data.get("family_size", 0))
        if family_size <= 0 or family_size > 25:
            errors.append("family_size must be a positive integer between 1 and 25")
    except (ValueError, TypeError):
        errors.append("family_size must be a valid integer")

    if not data.get("ration_card_type") or not str(data["ration_card_type"]).strip():
        errors.append("ration_card_type is required")

    return errors


def validate_commodity_payload(data):
    """Validates commodity payload."""
    errors = []
    if not data or not isinstance(data, dict):
        return ["Request body must be a valid JSON object"]
    if not data.get("name") or not str(data["name"]).strip():
        errors.append("Commodity name is required")
    if not data.get("commodity_code") or not str(data["commodity_code"]).strip():
        errors.append("commodity_code is required")
    return errors


def validate_inventory_payload(data):
    """Validates inventory payload."""
    errors = []
    if not data or not isinstance(data, dict):
        return ["Request body must be a valid JSON object"]
    if not data.get("commodity"):
        errors.append("commodity is required")
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
    if not data.get("commodity"):
        errors.append("commodity is required")
    try:
        qty = float(data.get("quantity", 0))
        if qty <= 0:
            errors.append("quantity must be greater than zero")
    except (ValueError, TypeError):
        errors.append("quantity must be a valid number")
    return errors
