from datetime import datetime


class InventoryModel:
    """Regional Inventory for a Commodity."""
    @staticmethod
    def create_doc(commodity, region, current_stock=0.0, unit="kg", buffer_stock=500.0, max_capacity=10000.0):
        return {
            "commodity": commodity.strip(),
            "region": region.strip(),
            "current_stock": float(current_stock),
            "unit": unit.strip().lower(),
            "buffer_stock": float(buffer_stock),
            "max_capacity": float(max_capacity),
            "last_updated": datetime.utcnow()
        }
