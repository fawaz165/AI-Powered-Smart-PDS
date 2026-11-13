from datetime import datetime


class BeneficiaryModel:
    """Beneficiary representation for PDS cardholders with configured entitlement rules."""
    VALID_CARD_TYPES = [
        "Antyodaya Anna Yojana (AAY)",
        "Priority (PHH)",
        "Non-Priority (NPHH)"
    ]

    # Configured NFSA Entitlement Rules per card type:
    # - AAY: Statutory NFSA 35 kg foodgrains per household/month (Rice 25kg, Wheat 10kg) + State welfare (Sugar 2kg, Dal 2kg)
    # - PHH: Statutory NFSA 5 kg foodgrains per person/month (Rice 5kg/person) + State welfare (Wheat 2kg/person, Sugar 1kg, Dal 1kg)
    # - NPHH: Non-NFSA (no statutory central quota); State-scheme allotment if configured (Rice 3kg/person, Wheat 1.5kg/person, Sugar 1kg, Dal 0.5kg)
    RATION_CARD_RULES = {
        "Antyodaya Anna Yojana (AAY)": {
            "mode": "fixed_family",
            "category": "AAY",
            "policy": "NFSA",
            "nfsa_foodgrains_kg": 35.0,
            "quotas": {"Rice": 25.0, "Wheat": 10.0, "Sugar": 2.0, "Dal": 2.0}
        },
        "Priority (PHH)": {
            "mode": "per_member",
            "category": "PHH",
            "policy": "NFSA",
            "nfsa_foodgrains_kg_per_person": 5.0,
            "per_member": {"Rice": 5.0, "Wheat": 2.0},
            "fixed_family": {"Sugar": 1.0, "Dal": 1.0}
        },
        "Non-Priority (NPHH)": {
            "mode": "per_member",
            "category": "NPHH",
            "policy": "STATE",
            "nfsa_foodgrains_kg_per_person": 0.0,
            "per_member": {"Rice": 3.0, "Wheat": 1.5},
            "fixed_family": {"Sugar": 1.0, "Dal": 0.5}
        }
    }

    @staticmethod
    def normalize_card_category(ration_card_type: str) -> str:
        """
        Robustly normalizes raw ration card type string into canonical category ('PHH', 'AAY', 'NPHH').
        Accounts for case differences, leading/trailing whitespace, punctuation, and substring permutations.
        Checks NPHH first to avoid substring collision with 'Priority' / 'PHH'.
        """
        s = str(ration_card_type or "").strip().upper()
        if "NPHH" in s or "NON-PRIORITY" in s or "NON PRIORITY" in s or "NON_PRIORITY" in s:
            return "NPHH"
        if "AAY" in s or "ANTYODAYA" in s or "ANNA YOJANA" in s:
            return "AAY"
        if "PHH" in s or "PRIORITY" in s:
            return "PHH"
        return "PHH"

    @classmethod
    def calculate_monthly_quota(cls, ration_card_type: str, family_size: int) -> dict:
        """Calculates monthly commodity entitlement quotas based on configured ration-card rules."""
        size = max(1, int(family_size))
        category = cls.normalize_card_category(ration_card_type)
        if category == "NPHH":
            matched_rule = cls.RATION_CARD_RULES["Non-Priority (NPHH)"]
        elif category == "AAY":
            matched_rule = cls.RATION_CARD_RULES["Antyodaya Anna Yojana (AAY)"]
        else:
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
    def get_entitlement_breakdown(cls, ration_card_type: str, family_size: int, custom_quota: dict = None) -> dict:
        """
        Calculates statutory NFSA foodgrain entitlement and separate State-scheme/demo allocations:
        - PHH: Statutory NFSA = Family size × 5.0 kg foodgrains per person per month.
               Additional state/demo welfare: Wheat (2.0 kg/person), Sugar (1.0 kg), Dal (1.0 kg).
        - AAY: Statutory NFSA = 35.0 kg foodgrains per household per month (Fixed: Rice 25kg, Wheat 10kg).
               Additional state/demo welfare: Sugar (2.0 kg), Dal (2.0 kg).
        - NPHH: Non-NFSA (no statutory central quota asserted).
               State-scheme: Rice (3 kg/person), Wheat (1.5 kg/person), Sugar (1 kg), Dal (0.5 kg) if configured,
               or 'State scheme – not configured'.
        Guarantees: Never displays 0 kg when valid entitlement data exists.
        """
        size = max(1, int(family_size or 1))
        category = cls.normalize_card_category(ration_card_type)
        total_quota = cls.calculate_monthly_quota(ration_card_type, size)

        # If custom quota is provided and contains valid quantities, preserve them
        if custom_quota and isinstance(custom_quota, dict) and any(float(v or 0) > 0 for v in custom_quota.values()):
            for k, v in custom_quota.items():
                try:
                    total_quota[k] = float(v)
                except (ValueError, TypeError):
                    pass

        if category == "PHH":
            nfsa_kg = round(size * 5.0, 1)
            nfsa_label = f"NFSA: {int(nfsa_kg) if nfsa_kg.is_integer() else nfsa_kg} kg/mo"
            nfsa_formula = f"({size} member{'s' if size > 1 else ''} × 5 kg/person)"
            # Statutory foodgrains is Rice (5kg/person). Any additional commodities are state/demo welfare
            state_welfare = {}
            for comm, qty in total_quota.items():
                if comm == "Rice":
                    continue
                if float(qty or 0) > 0:
                    state_welfare[comm] = round(float(qty), 1)

            state_welfare_text = ", ".join(f"{c} {int(q) if q.is_integer() else q}kg" for c, q in state_welfare.items()) or "None configured"

            return {
                "category": "PHH",
                "policy": "NFSA",
                "is_nfsa": True,
                "family_size": size,
                "statutory_foodgrains_kg": nfsa_kg,
                "statutory_label": nfsa_label,
                "statutory_formula": nfsa_formula,
                "statutory_description": f"Statutory NFSA: {int(nfsa_kg) if nfsa_kg.is_integer() else nfsa_kg} kg/month {nfsa_formula}",
                "state_allocations": state_welfare,
                "state_allocations_text": state_welfare_text,
                "monthly_quota": total_quota
            }

        elif category == "AAY":
            nfsa_kg = 35.0
            nfsa_label = "NFSA: 35 kg/mo"
            nfsa_formula = "(Fixed 35 kg/household)"
            # Statutory 35kg consists of Rice (25kg) + Wheat (10kg) = 35kg foodgrains
            state_welfare = {}
            for comm, qty in total_quota.items():
                if comm in ("Rice", "Wheat", "Foodgrains"):
                    continue
                if float(qty or 0) > 0:
                    state_welfare[comm] = round(float(qty), 1)

            state_welfare_text = ", ".join(f"{c} {int(q) if q.is_integer() else q}kg" for c, q in state_welfare.items()) or "None configured"

            return {
                "category": "AAY",
                "policy": "NFSA",
                "is_nfsa": True,
                "family_size": size,
                "statutory_foodgrains_kg": nfsa_kg,
                "statutory_label": nfsa_label,
                "statutory_formula": nfsa_formula,
                "statutory_description": "Statutory NFSA: 35 kg/month (Fixed 35 kg/household)",
                "state_allocations": state_welfare,
                "state_allocations_text": state_welfare_text,
                "monthly_quota": total_quota
            }

        else:  # NPHH
            has_allocations = any(float(v or 0) > 0 for v in total_quota.values())
            state_welfare = {c: round(float(q), 1) for c, q in total_quota.items() if float(q or 0) > 0}
            state_welfare_text = (
                ", ".join(f"{c} {int(q) if q.is_integer() else q}kg" for c, q in state_welfare.items())
                if has_allocations else "State scheme – not configured"
            )

            return {
                "category": "NPHH",
                "policy": "STATE",
                "is_nfsa": False,
                "family_size": size,
                "statutory_foodgrains_kg": None,
                "statutory_label": "Non-NFSA",
                "statutory_formula": "(No statutory central quota)",
                "statutory_description": "Non-Priority Household (No statutory central quota)",
                "state_allocations": state_welfare,
                "state_allocations_text": state_welfare_text,
                "monthly_quota": total_quota
            }

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
