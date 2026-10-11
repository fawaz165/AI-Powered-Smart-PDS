from datetime import datetime


class CommodityModel:
    """Commodity representation (Rice, Wheat, Sugar, Dal) with official vs demo rate classifications."""
    VALID_RATE_TYPES = ["OFFICIAL_NFSA", "DEMONSTRATION", "STATE_SUBSIDY"]

    @staticmethod
    def create_doc(commodity_code, name, unit="kg", subsidized_price=0.0, description=None,
                   rate_type="OFFICIAL_NFSA", market_price=None):
        sub_price = float(subsidized_price)
        mkt_price = float(market_price) if market_price is not None else round(max(sub_price * 3.5, 30.0), 2)
        rtype = str(rate_type).strip().upper() if rate_type else "OFFICIAL_NFSA"
        if rtype not in CommodityModel.VALID_RATE_TYPES:
            rtype = "OFFICIAL_NFSA"

        return {
            "commodity_code": commodity_code.strip().upper(),
            "name": name.strip(),
            "unit": unit.strip().lower(),
            "subsidized_price": sub_price,
            "market_price": mkt_price,
            "rate_type": rtype,
            "is_demonstration": (rtype == "DEMONSTRATION"),
            "description": description or f"Essential PDS staple grain: {name}",
            "created_at": datetime.utcnow()
        }
