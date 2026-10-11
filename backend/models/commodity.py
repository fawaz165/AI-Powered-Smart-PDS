from datetime import datetime


class CommodityModel:
    """Commodity representation (Rice, Wheat, Sugar, Dal) with official vs demo rate classifications."""
    VALID_RATE_TYPES = ["OFFICIAL_NFSA", "DEMONSTRATION", "STATE_SUBSIDY"]

    @staticmethod
    def create_doc(commodity_code, name, unit="kg", subsidized_price=0.0, description=None,
                   rate_type="OFFICIAL_NFSA", market_price=None, is_demonstration=None):
        code = commodity_code.strip().upper()
        comm_name = name.strip()
        sub_price = max(0.0, float(subsidized_price))
        mkt_price = float(market_price) if market_price is not None else round(max(sub_price * 3.5, 30.0), 2)
        rtype = str(rate_type).strip().upper() if rate_type else "DEMONSTRATION"
        if rtype not in CommodityModel.VALID_RATE_TYPES:
            rtype = "DEMONSTRATION"

        # Calculate subsidy savings and discount percentage
        subsidy_amount = round(max(0.0, mkt_price - sub_price), 2) if mkt_price else 0.0
        subsidy_percentage = round(min(100.0, max(0.0, (subsidy_amount / mkt_price) * 100)), 2) if mkt_price and mkt_price > 0 else 0.0

        # Verification: Only verified NFSA grains within statutory issue caps are marked official
        is_official = (rtype == "OFFICIAL_NFSA")
        is_verified = bool(is_official and (code in ["COM-RIC", "COM-WHT", "COM-SUG"] or sub_price <= 13.5))
        if is_demonstration is not None:
            demo_flag = bool(is_demonstration)
        else:
            demo_flag = bool(rtype == "DEMONSTRATION")

        return {
            "commodity_code": code,
            "name": comm_name,
            "unit": unit.strip().lower(),
            "subsidized_price": sub_price,
            "market_price": mkt_price,
            "subsidy_amount": subsidy_amount,
            "subsidy_percentage": subsidy_percentage,
            "rate_type": rtype,
            "is_demonstration": demo_flag,
            "is_verified": is_verified,
            "description": description or f"Essential PDS staple grain: {comm_name}",
            "created_at": datetime.utcnow()
        }
