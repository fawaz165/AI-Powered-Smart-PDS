from datetime import datetime


class BeneficiaryModel:
    """Beneficiary representation for PDS cardholders with configured entitlement rules."""
    VALID_CARD_TYPES = [
        "Antyodaya Anna Yojana (AAY)",
        "Priority (PHH)",
        "Non-Priority (NPHH)"
    ]

    # Configured NFSA Entitlement Rules per card type:
    # - AAY: Fixed family monthly allocation (Rice 25kg, Wheat 10kg, Sugar 2kg, Dal 2kg)
    # - PHH: Per-member entitlement (Rice 5kg/person, Wheat 2kg/person, Sugar 1kg, Dal 1kg)
    # - NPHH: Per-member basic allotment (Rice 3kg/person, Wheat 1.5kg/person, Sugar 1kg, Dal 0.5kg)
    RATION_CARD_RULES = {
        "Antyodaya Anna Yojana (AAY)": {
            "mode": "fixed_family",
            "quotas": {"Rice": 25.0, "Wheat": 10.0, "Sugar": 2.0, "Dal": 2.0}
        },
        "Priority (PHH)": {
            "mode": "per_member",
            "per_member": {"Rice": 5.0, "Wheat": 2.0},
            "fixed_family": {"Sugar": 1.0, "Dal": 1.0}
        },
        "Non-Priority (NPHH)": {
            "mode": "per_member",
            "per_member": {"Rice": 3.0, "Wheat": 1.5},
            "fixed_family": {"Sugar": 1.0, "Dal": 0.5}
        }
    }

    @classmethod
    def calculate_monthly_quota(cls, ration_card_type: str, family_size: int) -> dict:
        """Calculates monthly commodity entitlement quotas based on configured ration-card rules."""
        size = max(1, int(family_size))
        matched_rule = None
        for key, rule in cls.RATION_CARD_RULES.items():
            if key.lower() in ration_card_type.lower() or ration_card_type.lower() in key.lower():
                matched_rule = rule
                break
        if not matched_rule:
            matched_rule = cls.RATION_CARD_RULES["Priority (PHH)"]

        if matched_rule["mode"] == "fixed_family":
            return dict(matched_rule["quotas"])

        quota = {}
        for comm, per_person in matched_rule.get("per_member", {}).items():
            quota[comm] = round(size * per_person, 1)
        for comm, fixed_qty in matched_rule.get("fixed_family", {}).items():
            quota[comm] = fixed_qty
        return quota

    @classmethod
    def create_doc(cls, beneficiary_id, name, region, family_size, ration_card_type, ration_card_number=None, monthly_quota=None):
        size = int(family_size)
        if not monthly_quota:
            monthly_quota = cls.calculate_monthly_quota(ration_card_type, size)

        return {
            "beneficiary_id": beneficiary_id.strip().upper(),
            "name": name.strip(),
            "region": region.strip(),
            "family_size": size,
            "ration_card_type": ration_card_type.strip(),
            "ration_card_number": (ration_card_number or f"RC-{beneficiary_id}").strip().upper(),
            "monthly_quota": monthly_quota,
            "created_at": datetime.utcnow(),
            "status": "Active"
        }
