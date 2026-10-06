from datetime import datetime


class BeneficiaryModel:
    """Beneficiary representation for PDS cardholders."""
    VALID_CARD_TYPES = ["Antyodaya Anna Yojana (AAY)", "Priority (PHH)", "Non-Priority (NPHH)"]

    @staticmethod
    def create_doc(beneficiary_id, name, region, family_size, ration_card_type, ration_card_number=None, monthly_quota=None):
        if not monthly_quota:
            # Default monthly quotas (in kg) based on card type and family size
            if "AAY" in ration_card_type:
                monthly_quota = {"Rice": 25.0, "Wheat": 10.0, "Sugar": 2.0, "Dal": 2.0}
            elif "Priority" in ration_card_type:
                monthly_quota = {
                    "Rice": round(family_size * 5.0, 1),
                    "Wheat": round(family_size * 2.0, 1),
                    "Sugar": 1.0,
                    "Dal": 1.0
                }
            else:
                monthly_quota = {
                    "Rice": round(family_size * 3.0, 1),
                    "Wheat": round(family_size * 1.5, 1),
                    "Sugar": 1.0,
                    "Dal": 0.5
                }

        return {
            "beneficiary_id": beneficiary_id.strip().upper(),
            "name": name.strip(),
            "region": region.strip(),
            "family_size": int(family_size),
            "ration_card_type": ration_card_type.strip(),
            "ration_card_number": (ration_card_number or f"RC-{beneficiary_id}").strip().upper(),
            "monthly_quota": monthly_quota,
            "created_at": datetime.utcnow(),
            "status": "Active"
        }
