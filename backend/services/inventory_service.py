import threading
import re
from datetime import datetime, timedelta, timezone
from pymongo import ReturnDocument
from backend.database.mongo import get_db
from backend.models.inventory import InventoryModel
from backend.utils.logger import logger


class InventoryService:
    """Thread-safe inventory management service utilizing threading.Lock to eliminate race conditions."""
    _lock = threading.Lock()

    @classmethod
    def get_stock(cls, commodity: str, region: str) -> dict:
        """Retrieves stock document for a given commodity and region."""
        db = get_db()
        return db.inventory.find_one({
            "$or": [
                {"commodity": {"$regex": f"^{re.escape(commodity)}$", "$options": "i"}},
                {"commodity_code": commodity.strip().upper()}
            ],
            "region": {"$regex": f"^{re.escape(region)}$", "$options": "i"}
        })

    @classmethod
    def update_stock(cls, commodity: str, region: str, new_stock: float, user: str = None):
        """
        Direct administrative update of stock level with validation preventing negative values,
        audit logging to db.inventory_audit, adjustment history preservation, and timestamp recording.
        """
        try:
            new_stock = float(new_stock)
        except (ValueError, TypeError):
            raise ValueError("Inventory stock level must be numeric.")

        if new_stock < 0:
            raise ValueError("Inventory stock level cannot be negative.")

        with cls._lock:
            db = get_db()
            inv = db.inventory.find_one({
                "$or": [
                    {"commodity": {"$regex": f"^{re.escape(commodity)}$", "$options": "i"}},
                    {"commodity_code": commodity.strip().upper()}
                ],
                "region": {"$regex": f"^{re.escape(region)}$", "$options": "i"}
            })

            now_dt = datetime.utcnow()
            responsible_user = user or "Administrator"
            resolved_commodity = inv.get("commodity", commodity) if inv else commodity
            commodity_code = inv.get("commodity_code") if inv else None
            previous_stock = float(inv.get("current_stock", 0.0)) if inv else 0.0
            difference = round(new_stock - previous_stock, 2)

            audit_entry = {
                "commodity": resolved_commodity,
                "commodity_code": commodity_code,
                "region": region,
                "previous_stock": previous_stock,
                "new_stock": round(new_stock, 2),
                "difference": difference,
                "timestamp": now_dt,
                "updated_by": responsible_user,
                "action": "MANUAL_STOCK_ADJUSTMENT"
            }

            if inv:
                db.inventory.update_one(
                    {"_id": inv["_id"]},
                    {
                        "$set": {
                            "current_stock": round(new_stock, 2),
                            "previous_stock": previous_stock,
                            "last_updated": now_dt,
                            "updated_by": responsible_user
                        },
                        "$push": {
                            "adjustment_history": {
                                "$each": [audit_entry],
                                "$slice": -50  # Retain recent 50 adjustments
                            }
                        }
                    }
                )
            else:
                doc = InventoryModel.create_doc(commodity=commodity, region=region, current_stock=round(new_stock, 2))
                doc["previous_stock"] = 0.0
                doc["updated_by"] = responsible_user
                doc["adjustment_history"] = [audit_entry]
                db.inventory.insert_one(doc)

            # Insert into standalone audit collection for immutable history logs
            try:
                db.inventory_audit.insert_one(audit_entry)
            except Exception as e:
                logger.warning(f"Could not write to inventory_audit collection: {e}")

            logger.info(
                f"[Stock Update] {resolved_commodity} in {region} updated from {previous_stock} kg "
                f"to {round(new_stock, 2)} kg (Delta: {difference:+} kg) by {responsible_user}."
            )

            return {
                "success": True,
                "commodity": resolved_commodity,
                "commodity_code": commodity_code,
                "region": region,
                "previous_stock": previous_stock,
                "current_stock": round(new_stock, 2),
                "difference": difference,
                "updated_by": responsible_user,
                "last_updated": now_dt.isoformat()
            }

    @classmethod
    def process_transaction_distribution(cls, commodity: str, region: str, quantity: float,
                                         beneficiary_id: str, ration_shop_id: str,
                                         anomaly_info: dict = None,
                                         entitlement_info: dict = None) -> dict:
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
            # 1. Fetch current stock within lock supporting commodity name or code
            inv = db.inventory.find_one({
                "$or": [
                    {"commodity": {"$regex": f"^{re.escape(commodity)}$", "$options": "i"}},
                    {"commodity_code": commodity.strip().upper()}
                ],
                "region": {"$regex": f"^{re.escape(region)}$", "$options": "i"}
            })
            if not inv:
                return {
                    "success": False,
                    "message": f"Inventory record not found for {commodity} in region '{region}'."
                }

            resolved_commodity = inv.get("commodity", commodity)
            commodity_code = inv.get("commodity_code")

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

            # 2. Atomic conditional stock deduction guaranteeing non-negative inventory
            deducted_doc = db.inventory.find_one_and_update(
                {
                    "_id": inv["_id"],
                    "current_stock": {"$gte": quantity}
                },
                {
                    "$inc": {"current_stock": -round(quantity, 2)},
                    "$set": {"last_updated": datetime.utcnow()}
                },
                return_document=ReturnDocument.AFTER
            )
            if not deducted_doc:
                logger.warning(
                    f"Transaction rejected: Concurrently depleted stock for {commodity} in {region}."
                )
                return {
                    "success": False,
                    "message": f"Insufficient stock. Warehouse inventory was depleted during transaction processing.",
                    "available_stock": 0.0,
                    "shortfall": quantity
                }

            new_stock = round(float(deducted_doc.get("current_stock", 0.0)), 2)

            # 3. Generate transaction record
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

            now_dt = datetime.utcnow()
            audit_events = [
                {
                    "step": 1,
                    "action": "VALIDATION_PASSED",
                    "timestamp": now_dt.isoformat(),
                    "details": f"Beneficiary {beneficiary_id} eligible, sufficient stock verified ({current_stock} kg available)"
                },
                {
                    "step": 2,
                    "action": "ML_ANOMALY_ASSESSED",
                    "timestamp": now_dt.isoformat(),
                    "details": f"Status: {status}, Risk: {risk_level}, Score: {anomaly_score}"
                },
                {
                    "step": 3,
                    "action": "STOCK_DEDUCTED_ATOMIC",
                    "timestamp": now_dt.isoformat(),
                    "details": f"Inventory updated atomically from {current_stock} kg to {new_stock} kg (-{quantity} kg)"
                },
                {
                    "step": 4,
                    "action": "TRANSACTION_COMPLETED",
                    "timestamp": now_dt.isoformat(),
                    "details": f"Transaction {txn_id} committed to ledger"
                }
            ]

            entitlement_info = entitlement_info or {}
            entitled_quota = entitlement_info.get("entitled_quota")
            already_distributed = entitlement_info.get("already_distributed")
            remaining_entitlement = entitlement_info.get("remaining_entitlement")

            txn_doc = TransactionModel.create_doc(
                transaction_id=txn_id,
                beneficiary_id=beneficiary_id,
                ration_shop_id=ration_shop_id,
                commodity=resolved_commodity,
                commodity_code=commodity_code,
                quantity=quantity,
                region=region,
                timestamp=now_dt,
                status=status,
                risk_level=risk_level,
                anomaly_score=anomaly_score,
                reason=reason,
                processing_status="COMPLETED",
                previous_stock=current_stock,
                remaining_stock=new_stock,
                entitled_quota=entitled_quota,
                already_distributed=already_distributed,
                remaining_entitlement=remaining_entitlement,
                audit_trail=audit_events
            )

            try:
                db.transactions.insert_one(txn_doc)
            except Exception as e:
                # Rollback deducted stock atomically to preserve consistency
                db.inventory.update_one({"_id": inv["_id"]}, {"$inc": {"current_stock": quantity}})
                logger.error(f"Transaction insertion failed for {txn_id}, stock rolled back: {e}")
                raise e

            # If transaction is anomalous, also log to fraud_alerts collection
            if status != "NORMAL":
                db.fraud_alerts.update_one(
                    {"transaction_id": txn_id},
                    {"$set": {
                        "transaction_id": txn_id,
                        "beneficiary_id": beneficiary_id,
                        "ration_shop_id": ration_shop_id,
                        "commodity": resolved_commodity,
                        "commodity_code": commodity_code,
                        "quantity": quantity,
                        "region": region,
                        "risk_level": risk_level,
                        "anomaly_score": anomaly_score,
                        "score_interpretation": anomaly_info.get("score_interpretation"),
                        "score_badge": anomaly_info.get("score_badge"),
                        "entitled_quota": entitled_quota if entitled_quota is not None else anomaly_info.get("entitled_quota"),
                        "remaining_entitlement": remaining_entitlement,
                        "already_distributed": already_distributed,
                        "quantity_to_quota_ratio": anomaly_info.get("quantity_to_quota_ratio"),
                        "status": "PENDING_REVIEW",
                        "review_decision": None,
                        "reviewed_by": None,
                        "reviewed_at": None,
                        "review_history": [],
                        "reason": reason,
                        "created_at": datetime.utcnow()
                    }},
                    upsert=True
                )

            logger.info(
                f"[Thread-Safe Inventory] Deducted {quantity} kg {resolved_commodity} ({commodity_code}) in {region}. "
                f"Previous: {current_stock} kg, New: {new_stock} kg. Txn: {txn_id}"
            )

            return {
                "success": True,
                "transaction_id": txn_id,
                "commodity": resolved_commodity,
                "commodity_code": commodity_code,
                "region": region,
                "quantity_distributed": quantity,
                "previous_stock": current_stock,
                "remaining_stock": new_stock,
                "entitled_quota": entitled_quota,
                "already_distributed": already_distributed,
                "remaining_entitlement": remaining_entitlement,
                "status": status,
                "risk_level": risk_level,
                "reason": reason
            }

    @classmethod
    def calculate_inventory_alerts(cls, predicted_demand_map: dict = None, include_safety_stock: bool = False,
                                   region: str = None, commodity: str = None) -> list:
        """
        Compares current stock with buffer stock and predicted demand.
        Detects:
        - Critical shortages (stock < buffer or stock < predicted demand)
        - Recommended procurement quantity (satisfies demand; incorporates safety stock only when configured)
        - Excess stock (stock > 1.5x predicted demand)
        - Supports optional district (region) and commodity filtering.
        """
        db = get_db()
        query = {}
        if region and region.strip().upper() != "ALL":
            query["region"] = {"$regex": f"^{re.escape(region.strip())}$", "$options": "i"}
        if commodity and commodity.strip().upper() != "ALL":
            comm_clean = commodity.strip()
            query["$or"] = [
                {"commodity": {"$regex": f"^{re.escape(comm_clean)}$", "$options": "i"}},
                {"commodity_code": comm_clean.upper()}
            ]

        items = list(db.inventory.find(query, {"_id": 0}))
        alerts = []

        predicted_demand_map = predicted_demand_map or {}
        now = datetime.utcnow()
        forecast_month = now.month + 1
        forecast_year = now.year
        if forecast_month > 12:
            forecast_month = 1
            forecast_year += 1
        forecast_period = f"{forecast_year:04d}-{forecast_month:02d}"
        month_names = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        forecast_label = f"{month_names[forecast_month]} {forecast_year}"

        # Supply the model with observed database features rather than fixed demo inputs.
        beneficiary_stats = {}
        allocations = {}
        for beneficiary in db.beneficiaries.find({}, {"_id": 0, "region": 1, "family_size": 1, "monthly_quota": 1}):
            region_key = beneficiary.get("region", "")
            stats = beneficiary_stats.setdefault(region_key, {"count": 0, "family_total": 0})
            stats["count"] += 1
            stats["family_total"] += int(beneficiary.get("family_size", 0) or 0)
            for name, amount in (beneficiary.get("monthly_quota") or {}).items():
                key = (region_key, name.lower())
                allocations[key] = allocations.get(key, 0.0) + float(amount or 0)

        history_start = now - timedelta(days=90)
        history_by_key = {}
        for txn in db.transactions.find(
            {"timestamp": {"$gte": history_start, "$lt": now}},
            {"_id": 0, "commodity": 1, "region": 1, "quantity": 1, "timestamp": 1}
        ):
            stamp = txn.get("timestamp")
            if isinstance(stamp, str):
                try:
                    parsed_stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    stamp = parsed_stamp.astimezone(timezone.utc).replace(tzinfo=None) if parsed_stamp.tzinfo else parsed_stamp
                except ValueError:
                    continue
            if not isinstance(stamp, datetime):
                continue
            key = (txn.get("commodity", "").lower(), txn.get("region", ""))
            slot = history_by_key.setdefault(key, {"last_30_days": 0.0, "last_90_days": 0.0})
            quantity = float(txn.get("quantity", 0) or 0)
            slot["last_90_days"] += quantity
            if stamp >= now - timedelta(days=30):
                slot["last_30_days"] += quantity

        for item in items:
            commodity = item.get("commodity")
            commodity_code = item.get("commodity_code")
            if not commodity_code:
                code_map = {"Rice": "COM-RIC", "Wheat": "COM-WHT", "Sugar": "COM-SUG", "Dal": "COM-DAL"}
                commodity_code = code_map.get(commodity, f"COM-{commodity[:3].upper()}")
            region_name = item.get("region")
            stock = float(item.get("current_stock", 0))
            buffer = float(item.get("buffer_stock", 500))

            # Look up predicted demand from explicit map or compute via MLService
            pred_key = f"{commodity}_{region_name}"
            predicted_demand = predicted_demand_map.get(pred_key)
            prediction_available = True
            raw_pred_val = None
            is_insufficient = False
            data_warning = None

            if predicted_demand is None:
                try:
                    from backend.services.ml_service import MLService
                    stats = beneficiary_stats.get(region_name, {"count": 0, "family_total": 0})
                    sample_size = stats.get("count", 0)
                    history = history_by_key.get((str(commodity).lower(), region_name), {})
                    prior_month_demand = history.get("last_30_days", 0.0)
                    pred_output = MLService.predict_demand({
                        "commodity": commodity,
                        "commodity_code": commodity_code,
                        "region": region_name,
                        "month": forecast_month,
                        "year": forecast_year,
                        "beneficiary_count": stats["count"],
                        "avg_family_size": (stats["family_total"] / stats["count"]) if stats["count"] else 0,
                        "previous_demand": prior_month_demand,
                        "previous_offtake": prior_month_demand,
                        "historical_average_3m": history.get("last_90_days", 0.0) / 3.0,
                        "allocated_quota": allocations.get((region_name, str(commodity).lower()), 0.0),
                        "current_stock": stock,
                        "safety_stock": buffer
                    }, save_audit=False)
                    predicted_demand = float(pred_output.get("predicted_demand", 0.0))
                    raw_pred_val = pred_output.get("calculation_breakdown", {}).get("raw_pipeline_prediction")

                    # Validate prediction against sample size & identify negative/unusually small outputs
                    if raw_pred_val is not None and float(raw_pred_val) <= 0:
                        is_insufficient = True
                        data_warning = (
                            f"Notice: Sparse cardholder sample size ({sample_size} registered in {region_name}). "
                            f"Raw model output was non-positive ({float(raw_pred_val):.1f} kg); high forecast uncertainty. Genuine monthly demand is not zero."
                        )
                    elif sample_size < 5 and predicted_demand < 50.0:
                        is_insufficient = True
                        data_warning = (
                            f"Notice: Unusually low predicted demand ({predicted_demand:.1f} kg) "
                            f"due to small demographic sample size ({sample_size} registered cardholder(s))."
                        )
                except Exception as exc:
                    logger.warning(f"Demand forecast unavailable for {commodity} in {region_name}: {exc}")
                    predicted_demand = None
                    prediction_available = False

            if predicted_demand is not None and float(predicted_demand) <= 0.0:
                is_insufficient = True
                if not data_warning:
                    data_warning = (
                        f"Notice: Non-positive predicted demand ({float(predicted_demand):.1f} kg). "
                        f"Genuine monthly foodgrain demand is not zero."
                    )

            if not prediction_available:
                alerts.append({
                    "commodity": commodity, "commodity_code": commodity_code, "region": region_name,
                    "current_stock": round(stock, 2), "predicted_demand": None,
                    "difference": None,
                    "buffer_stock": round(buffer, 2), "shortage": 0.0,
                    "recommended_procurement": 0.0, "safety_stock_included": bool(include_safety_stock),
                    "prediction_available": False, "forecast_period": forecast_period,
                    "forecast_label": forecast_label,
                    "demand_period": "MONTHLY",
                    "demand_unit": "kg/month",
                    "forecast_timeframe": f"Monthly Forecast ({forecast_label})",
                    "is_zero_demand": False,
                    "status": "UNAVAILABLE", "classification": "Unavailable", "alert_level": "NOTICE",
                    "insufficient_data": True,
                    "data_quality_warning": "Demand forecast unavailable; no substitute value was used.",
                    "message": "Demand forecast unavailable; no substitute value was used."
                })
                continue

            predicted_demand = float(predicted_demand)

            # Difference = Current Stock - Predicted Demand
            difference = round(stock - predicted_demand, 2)
            raw_shortage = round(predicted_demand - stock, 2)
            shortage = round(max(0.0, raw_shortage), 2)

            # Procurement Required = max(0, Predicted Demand - Current Stock)
            # Consistent procurement calculation: include safety buffer only when configured
            if include_safety_stock:
                gross_target = round(predicted_demand + buffer, 2)
                recommended_procurement = round(max(0.0, gross_target - stock), 2)
            else:
                recommended_procurement = shortage

            # Three clear statuses: Shortage, Sufficient, Surplus
            if shortage > 0:
                status = "SHORTAGE"
                classification = "Shortage"
                alert_level = "CRITICAL" if stock <= buffer else "WARNING"
                if include_safety_stock and buffer > 0:
                    msg = f"Potential shortage of {shortage:,.1f} kg detected. Recommended procurement: {recommended_procurement:,.1f} kg (satisfies demand + {buffer} kg safety buffer)."
                else:
                    msg = f"Stock deficit of {shortage:,.1f} kg below anticipated monthly demand ({predicted_demand:,.1f} kg). Procurement required: {recommended_procurement:,.1f} kg."
            else:
                if include_safety_stock and stock < (predicted_demand + buffer):
                    status = "SHORTAGE" if recommended_procurement > 0 else "SUFFICIENT"
                    classification = "Shortage" if recommended_procurement > 0 else "Sufficient"
                    alert_level = "WARNING"
                    msg = f"Stock ({stock:,.1f} kg) meets predicted demand ({predicted_demand:,.1f} kg), but buffer deficit requires {recommended_procurement:,.1f} kg replenishment."
                elif stock > (predicted_demand * 1.5):
                    status = "SURPLUS"
                    classification = "Surplus"
                    alert_level = "NOTICE"
                    surplus_qty = round(stock - predicted_demand, 2)
                    msg = f"Surplus inventory detected: {surplus_qty:,.1f} kg above anticipated monthly demand ({predicted_demand:,.1f} kg)."
                else:
                    status = "SUFFICIENT"
                    classification = "Sufficient"
                    alert_level = "NORMAL"
                    msg = f"Stock levels ({stock:,.1f} kg) meet anticipated monthly demand ({predicted_demand:,.1f} kg)."

            alerts.append({
                "commodity": commodity,
                "commodity_code": commodity_code,
                "region": region_name,
                "current_stock": round(stock, 2),
                "predicted_demand": round(predicted_demand, 2),
                "difference": difference,
                "buffer_stock": round(buffer, 2),
                "shortage": shortage,
                "recommended_procurement": recommended_procurement,
                "safety_stock_included": bool(include_safety_stock),
                "prediction_available": True,
                "forecast_period": forecast_period,
                "forecast_label": forecast_label,
                "demand_period": "MONTHLY",
                "demand_unit": "kg/month",
                "forecast_timeframe": f"Monthly Forecast ({forecast_label})",
                "is_zero_demand": (predicted_demand == 0.0),
                "status": status,
                "status_legacy": "EXCESS" if status == "SURPLUS" else status,
                "classification": classification,
                "alert_level": alert_level,
                "insufficient_data": is_insufficient,
                "data_quality_warning": data_warning,
                "raw_pipeline_prediction": raw_pred_val,
                "message": msg
            })

        return alerts
