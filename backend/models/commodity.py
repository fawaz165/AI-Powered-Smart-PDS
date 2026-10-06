from datetime import datetime


class CommodityModel:
    """Commodity representation (Rice, Wheat, Sugar, Dal)."""
    @staticmethod
    def create_doc(commodity_code, name, unit="kg", subsidized_price=0.0, description=None):
        return {
            "commodity_code": commodity_code.strip().upper(),
            "name": name.strip(),
            "unit": unit.strip().lower(),
            "subsidized_price": float(subsidized_price),
            "description": description or f"Essential PDS staple grain: {name}",
            "created_at": datetime.utcnow()
        }
