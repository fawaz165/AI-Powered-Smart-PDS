import threading
from datetime import datetime
from backend.database.mongo import get_db
from backend.utils.logger import logger


class InventoryService:
    """Thread-safe inventory management service utilizing threading.Lock to eliminate race conditions."""
    _lock = threading.Lock()

    @classmethod
    def get_stock(cls, commodity: str, region: str) -> dict:
        """Retrieves stock document for a given commodity and region."""
        db = get_db()
        return db.inventory.find_one({"commodity": commodity, "region": region})

    @classmethod
    def update_stock(cls, commodity: str, region: str, new_stock: float):
        """Direct administrative update of stock level."""
        with cls._lock:
            db = get_db()
            db.inventory.update_one(
                {"commodity": commodity, "region": region},
                {"$set": {"current_stock": float(new_stock), "last_updated": datetime.utcnow()}},
                upsert=True
            )
            return True

    @classmethod
    def process_transaction_distribution(cls, commodity: str, region: str, quantity: float,
                                         beneficiary_id: str, ration_shop_id: str,
                                         anomaly_info: dict = None) -> dict:
        """
        Thread-safely deducts grain quantity from inventory and logs transaction.
        Enforces:
        1. Thread concurrency safety with threading.Lock
        2. Non-negative inventory verification
        3. Atomic inventory deduction
        """
        quantity = float(quantity)
        if quantity <= 0:
            return {"success": False, "message": "Distribution quantity must be positive."}

        with cls._lock:
            db = get_db()
            # 1. Fetch current stock within lock
            inv = db.inventory.find_one({"commodity": commodity, "region": region})
            if not inv:
                return {
                    "success": False,
                    "message": f"Inventory record not found for {commodity} in region '{region}'."
                }

            current_stock = float(inv.get("current_stock", 0.0))
            if current_stock < quantity:
                logger.warning(
                    f"Transaction rejected: Insufficient stock. Available: {current_stock} kg, Requested: {quantity} kg."
                )
                return {
                    "success": False,
                    "message": f"Insufficient stock. Available: {current_stock} kg, Requested: {quantity} kg.",
                    "available_stock": current_stock,
                    "shortfall": round(quantity - current_stock, 2)
                }

            # 2. Compute new stock safely
            new_stock = round(current_stock - quantity, 2)

            # 3. Update database inventory
            db.inventory.update_one(
                {"commodity": commodity, "region": region},
                {"$set": {"current_stock": new_stock, "last_updated": datetime.utcnow()}}
            )

            # 4. Generate transaction record
            from backend.models.transaction import TransactionModel
            import uuid

            txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
            status = "NORMAL"
            risk_level = "LOW"
            anomaly_score = 0.0
            reason = "Standard monthly quota collection"

            if anomaly_info:
                status = anomaly_info.get("status", "NORMAL")
                risk_level = anomaly_info.get("risk_level", "LOW")
                anomaly_score = anomaly_info.get("anomaly_score", 0.0)
                reason = anomaly_info.get("reason", reason)

            txn_doc = TransactionModel.create_doc(
                transaction_id=txn_id,
                beneficiary_id=beneficiary_id,
                ration_shop_id=ration_shop_id,
                commodity=commodity,
                quantity=quantity,
                region=region,
                timestamp=datetime.utcnow(),
                status=status,
                risk_level=risk_level,
                anomaly_score=anomaly_score,
                reason=reason
            )
            db.transactions.insert_one(txn_doc)

            # If transaction is anomalous, also log to fraud_alerts collection
            if status != "NORMAL":
                db.fraud_alerts.update_one(
                    {"transaction_id": txn_id},
                    {"$set": {
                        "transaction_id": txn_id,
                        "beneficiary_id": beneficiary_id,
                        "ration_shop_id": ration_shop_id,
                        "commodity": commodity,
                        "quantity": quantity,
                        "region": region,
                        "risk_level": risk_level,
                        "anomaly_score": anomaly_score,
                        "status": "PENDING_REVIEW",
                        "reason": reason,
                        "created_at": datetime.utcnow()
                    }},
                    upsert=True
                )

            logger.info(
                f"[Thread-Safe Inventory] Deducted {quantity} kg {commodity} in {region}. "
                f"Previous: {current_stock} kg, New: {new_stock} kg. Txn: {txn_id}"
            )

            return {
                "success": True,
                "transaction_id": txn_id,
                "commodity": commodity,
                "region": region,
                "quantity_distributed": quantity,
                "previous_stock": current_stock,
                "remaining_stock": new_stock,
                "status": status,
                "risk_level": risk_level,
                "reason": reason
            }

    @classmethod
    def calculate_inventory_alerts(cls, predicted_demand_map: dict = None) -> list:
        """
        Compares current stock with buffer stock and predicted demand.
        Detects:
        - Critical shortages (stock < buffer or stock < predicted demand)
        - Excess stock (stock > 1.5x predicted demand)
        - Recommended procurement quantity
        """
        db = get_db()
        items = list(db.inventory.find({}, {"_id": 0}))
        alerts = []

        predicted_demand_map = predicted_demand_map or {}

        for item in items:
            commodity = item.get("commodity")
            region = item.get("region")
            stock = float(item.get("current_stock", 0))
            buffer = float(item.get("buffer_stock", 500))

            # Look up predicted demand or default to heuristic based on card count
            pred_key = f"{commodity}_{region}"
            predicted_demand = predicted_demand_map.get(pred_key)
            if predicted_demand is None:
                # Heuristic default based on regional beneficiary card base
                card_count = db.beneficiaries.count_documents({"region": region}) or 500
                default_quota = 5.0 if commodity == "Rice" else (3.0 if commodity == "Wheat" else 1.0)
                predicted_demand = card_count * default_quota

            shortage = round(predicted_demand - stock, 2)
            if shortage > 0:
                status = "SHORTAGE"
                recommended_procurement = shortage
                alert_level = "CRITICAL" if stock <= buffer else "WARNING"
                msg = f"Potential shortage of {shortage} kg detected. Recommended procurement: {recommended_procurement} kg."
            else:
                recommended_procurement = 0.0
                if stock > (predicted_demand * 1.5):
                    status = "EXCESS"
                    alert_level = "NOTICE"
                    excess_qty = round(stock - predicted_demand, 2)
                    msg = f"Excess inventory detected: {excess_qty} kg above anticipated monthly demand."
                else:
                    status = "SUFFICIENT"
                    alert_level = "NORMAL"
                    msg = "Stock levels are optimal and sufficient to satisfy demand."

            alerts.append({
                "commodity": commodity,
                "region": region,
                "current_stock": stock,
                "predicted_demand": round(predicted_demand, 2),
                "buffer_stock": buffer,
                "shortage": max(0.0, shortage),
                "recommended_procurement": recommended_procurement,
                "status": status,
                "alert_level": alert_level,
                "message": msg
            })

        return alerts
