from datetime import datetime


class InventoryModel:
    """Regional Inventory for a Commodity."""
    @staticmethod
    def create_doc(commodity, region, current_stock=0.0, unit="kg", buffer_stock=500.0, max_capacity=10000.0, commodity_code=None):
        comm_name = commodity.strip()
        code = (commodity_code or (
            "COM-RIC" if comm_name.lower() == "rice" else (
                "COM-WHT" if comm_name.lower() == "wheat" else (
                    "COM-SUG" if comm_name.lower() == "sugar" else (
                        "COM-DAL" if comm_name.lower() == "dal" else f"COM-{comm_name[:3].upper()}"
                    )
                )
            )
        )).strip().upper()

        return {
            "commodity": comm_name,
            "commodity_code": code,
            "region": region.strip(),
            "current_stock": float(current_stock),
            "unit": unit.strip().lower(),
            "buffer_stock": float(buffer_stock),
            "max_capacity": float(max_capacity),
            "last_updated": datetime.utcnow()
        }
