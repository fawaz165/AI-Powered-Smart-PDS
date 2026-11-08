from datetime import datetime


class CommodityModel:
    """Commodity representation (Rice, Wheat, Sugar, Dal) with verified Tamil Nadu PDS scheme rates."""
    VALID_RATE_TYPES = ["OFFICIAL_NFSA", "STATE_SUBSIDY", "DEMONSTRATION"]

    @staticmethod
    def create_doc(commodity_code, name, unit="kg", subsidized_price=0.0, description=None,
                   rate_type="OFFICIAL_NFSA", market_price=None, is_demonstration=None,
                   category_pricing=None, official_source=None):
        code = commodity_code.strip().upper()
        comm_name = name.strip()
        sub_price = max(0.0, float(subsidized_price))
        mkt_price = float(market_price) if market_price is not None else round(max(sub_price * 3.5, 30.0), 2)
        rtype = str(rate_type).strip().upper() if rate_type else "DEMONSTRATION"
        if rtype not in CommodityModel.VALID_RATE_TYPES:
            rtype = "DEMONSTRATION"

        # Calculate subsidy savings and discount percentage against reference market benchmark
        subsidy_amount = round(max(0.0, mkt_price - sub_price), 2) if mkt_price else 0.0
        subsidy_percentage = round(min(100.0, max(0.0, (subsidy_amount / mkt_price) * 100)), 2) if mkt_price and mkt_price > 0 else 0.0

        # Verification: NFSA and verified Tamil Nadu State Welfare Subsidies (e.g. Special PDS Tur Dal, Free Rice/Wheat)
        if is_demonstration is not None:
            demo_flag = bool(is_demonstration)
        else:
            demo_flag = bool(rtype == "DEMONSTRATION")

        is_verified = bool(not demo_flag and (
            code in ["COM-RIC", "COM-WHT", "COM-SUG", "COM-DAL"] or
            rtype in ["OFFICIAL_NFSA", "STATE_SUBSIDY"]
        ))

        # Category-based pricing (e.g., Sugar: AAY ₹13.50/kg, PHH/NPHH ₹25.00/kg)
        default_category_pricing = None
        if code == "COM-SUG":
            default_category_pricing = {"AAY": 13.50, "PHH": 25.00, "NPHH": 25.00}
        elif code in ["COM-RIC", "COM-WHT"]:
            default_category_pricing = {"AAY": 0.0, "PHH": 0.0, "NPHH": 0.0}
        elif code == "COM-DAL":
            default_category_pricing = {"AAY": 30.0, "PHH": 30.0, "NPHH": 30.0}

        cat_pricing = category_pricing if isinstance(category_pricing, dict) else default_category_pricing

        # Official Scheme Source Documentation
        default_sources = {
            "COM-RIC": "Tamil Nadu Universal PDS & NFSA (Free Rice Scheme)",
            "COM-WHT": "Tamil Nadu PDS & PMGKAY (Free Entitlement for eligible cardholders)",
            "COM-SUG": "Central AAY Scheme (₹13.50/kg) & TNPDS State Order (₹25.00/kg for other cards)",
            "COM-DAL": "Tamil Nadu Special Public Distribution System (Special PDS Scheme, ₹30.00/kg)"
        }
        source_doc = official_source or default_sources.get(code) or ("National Food Security Act (NFSA)" if rtype == "OFFICIAL_NFSA" else "Tamil Nadu State Welfare Order")

        return {
            "commodity_code": code,
            "name": comm_name,
            "unit": unit.strip().lower(),
            "subsidized_price": sub_price,
            "market_price": mkt_price,
            "category_pricing": cat_pricing,
            "official_source": source_doc,
            "subsidy_amount": subsidy_amount,
            "subsidy_percentage": subsidy_percentage,
            "rate_type": rtype,
            "is_demonstration": demo_flag,
            "is_verified": is_verified,
            "description": description or f"Essential PDS staple grain: {comm_name}",
            "created_at": datetime.utcnow()
        }
