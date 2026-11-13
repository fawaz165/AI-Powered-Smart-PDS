from datetime import datetime
import re


class CommodityModel:
    """Commodity catalog record with explicit scheme classification and category prices."""

    VALID_SCHEME_CLASSIFICATIONS = ["NFSA", "TAMIL_NADU_STATE_PDS", "DEMO_CUSTOM"]
    VALID_RATE_TYPES = ["OFFICIAL_NFSA", "STATE_SUBSIDY", "DEMONSTRATION"]
    CATEGORY_KEYS = ("AAY", "PHH", "NPHH")
    LEGACY_TO_SCHEME = {
        "OFFICIAL_NFSA": "NFSA",
        "STATE_SUBSIDY": "TAMIL_NADU_STATE_PDS",
        "DEMONSTRATION": "DEMO_CUSTOM",
    }
    SCHEME_TO_LEGACY = {value: key for key, value in LEGACY_TO_SCHEME.items()}

    @classmethod
    def is_reliable_verification_source(cls, source: str) -> bool:
        """
        Validates whether a verification source is reliable.
        Must be a non-empty official URL (http/https) or recognized government/statutory reference.
        Rejects empty, generic, placeholder, or demonstration strings.
        """
        if not source:
            return False
        s = str(source).strip()
        if s.lower() in ("none", "null", "n/a", "na", "undefined", "unverified", "demo", "test", ""):
            return False
        if re.match(r"^https?://[^\s]+$", s, re.IGNORECASE):
            return True
        authority_keywords = ["act", "gov", "cooperative", "gazette", "order", "ministry", "department", "scale", "pds", "tn.gov", "nic.in"]
        if any(kw in s.lower() for kw in authority_keywords) and len(s) >= 8:
            return True
        return False

    @classmethod
    def normalize_scheme_classification(cls, value=None, legacy_rate_type=None):
        classification = str(value or "").strip().upper()
        if classification in cls.VALID_SCHEME_CLASSIFICATIONS:
            return classification
        legacy = str(legacy_rate_type or "").strip().upper()
        return cls.LEGACY_TO_SCHEME.get(legacy, "DEMO_CUSTOM")

    @classmethod
    def create_doc(cls, commodity_code, name, unit="kg", subsidized_price=None, description=None,
                   rate_type=None, market_price=None, is_demonstration=None,
                   category_pricing=None, official_source=None, scheme_classification=None,
                   verification_source=None, is_verified=False):
        code = commodity_code.strip().upper()
        comm_name = name.strip()
        requested_scheme = str(scheme_classification or "").strip().upper()
        rtype = str(rate_type or "").strip().upper()
        scheme = cls.normalize_scheme_classification(requested_scheme, rtype)
        if requested_scheme in cls.VALID_SCHEME_CLASSIFICATIONS or rtype not in cls.VALID_RATE_TYPES:
            rtype = cls.SCHEME_TO_LEGACY[scheme]

        prices = None
        if isinstance(category_pricing, dict):
            prices = {key: float(category_pricing[key]) for key in cls.CATEGORY_KEYS if key in category_pricing}
        legacy_price = float(subsidized_price) if subsidized_price not in (None, "") else None
        if legacy_price is None and prices and len(prices) == len(cls.CATEGORY_KEYS):
            legacy_price = min(prices.values())
        benchmark = float(market_price) if market_price not in (None, "") else None
        verification_ref = str(verification_source or "").strip() or None
        is_reliable = cls.is_reliable_verification_source(verification_ref)
        verified = bool(is_verified and scheme != "DEMO_CUSTOM" and is_reliable)
        demo = scheme == "DEMO_CUSTOM" if is_demonstration is None else bool(is_demonstration)
        if demo:
            scheme = "DEMO_CUSTOM"
            rtype = "DEMONSTRATION"
            verified = False

        return {
            "commodity_code": code,
            "name": comm_name,
            "unit": unit.strip().lower(),
            "subsidized_price": legacy_price,
            "market_price": benchmark,
            "category_pricing": prices,
            "rate_type": rtype,
            "scheme_classification": scheme,
            "official_source": str(official_source or "").strip() or None,
            "verification_source": verification_ref,
            "is_verified": verified,
            "is_demonstration": demo,
            "description": str(description or "").strip(),
            "created_at": datetime.utcnow(),
        }
