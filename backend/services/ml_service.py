import joblib
import json
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
from backend.config import Config
from backend.database.mongo import get_db
from backend.utils.logger import logger


class MLService:
    """Production ML Inference Service. Loads serialized models at startup to avoid repeated retraining."""
    _demand_model = None
    _demand_preprocessor = None
    _anomaly_model = None
    _anomaly_scaler = None
    _metrics = None

    @classmethod
    def load_models(cls):
        """Loads persistent model artifacts from disk into RAM if not already loaded."""
        if cls._demand_model is not None and cls._anomaly_model is not None:
            return
        model_dir = Config.MODEL_DIR
        try:
            demand_model_path = model_dir / "demand_model_best.joblib"
            preprocessor_path = model_dir / "demand_preprocessor.joblib"
            anomaly_model_path = model_dir / "anomaly_model_isolation_forest.joblib"
            anomaly_scaler_path = model_dir / "anomaly_scaler.joblib"
            metrics_path = model_dir / "model_metrics.json"

            if demand_model_path.exists() and preprocessor_path.exists():
                cls._demand_model = joblib.load(demand_model_path)
                cls._demand_preprocessor = joblib.load(preprocessor_path)
                logger.info(f"Loaded Demand Prediction model from {demand_model_path}")
            else:
                logger.warning("Demand model artifacts not found on disk.")

            if anomaly_model_path.exists() and anomaly_scaler_path.exists():
                cls._anomaly_model = joblib.load(anomaly_model_path)
                cls._anomaly_scaler = joblib.load(anomaly_scaler_path)
                logger.info(f"Loaded Anomaly Isolation Forest from {anomaly_model_path}")
            else:
                logger.warning("Anomaly model artifacts not found on disk.")

            if metrics_path.exists():
                with open(metrics_path, "r") as f:
                    cls._metrics = json.load(f)

        except Exception as e:
            logger.error(f"Error loading ML models: {e}")

    @classmethod
    def get_model_metrics(cls):
        """Returns loaded model evaluation benchmarks."""
        if cls._metrics is None:
            metrics_path = Config.MODEL_DIR / "model_metrics.json"
            if metrics_path.exists():
                with open(metrics_path, "r") as f:
                    cls._metrics = json.load(f)
        return cls._metrics or {}

    @classmethod
    def predict_demand(cls, data: dict) -> dict:
        """
        Executes ML demand inference and applies inventory logic:
        Predicted Demand - Current Stock = Shortage.
        """
        if cls._demand_model is None or cls._demand_preprocessor is None:
            cls.load_models()
            if cls._demand_model is None:
                raise RuntimeError("Demand ML model is not available.")

        commodity = data.get("commodity", "Rice").strip()
        region = data.get("region", "Chennai").strip()
        month = int(data.get("month", datetime.utcnow().month))
        beneficiary_count = int(data.get("beneficiary_count", 12500))
        previous_demand = float(data.get("previous_demand", 4200.0))
        current_stock = float(data.get("current_stock", 3800.0))
        
        # Inferred / default features
        avg_family_size = float(data.get("avg_family_size", 3.8))
        previous_offtake = float(data.get("previous_offtake", previous_demand * 0.96))
        hist_avg = float(data.get("historical_average_3m", previous_demand))
        allocated_quota = float(data.get("allocated_quota", previous_demand * 1.05))
        
        is_festive = 1 if (month == 1 or month in [10, 11]) else 0
        seasonal_index = 1.25 if (month == 1 and commodity in ["Rice", "Sugar"]) else (1.12 if is_festive else 1.0)

        # Assemble DataFrame matching preprocessor schema
        df_input = pd.DataFrame([{
            "commodity": commodity,
            "region": region,
            "month": month,
            "beneficiary_count": beneficiary_count,
            "avg_family_size": avg_family_size,
            "previous_month_demand": previous_demand,
            "previous_month_offtake": previous_offtake,
            "historical_average_3m": hist_avg,
            "current_stock": current_stock,
            "allocated_quota": allocated_quota,
            "is_festive_month": is_festive,
            "seasonal_index": seasonal_index
        }])

        X_transformed = cls._demand_preprocessor.transform(df_input)
        raw_pred = float(cls._demand_model.predict(X_transformed)[0])
        predicted_demand = round(max(0.0, raw_pred), 1)

        # Core Business Logic Calculation
        shortage = round(predicted_demand - current_stock, 1)

        if shortage > 0:
            status = "SHORTAGE"
            recommended_procurement = shortage
            message = f"Potential shortage: {shortage} kg. Recommended procurement: {recommended_procurement} kg."
        else:
            recommended_procurement = 0.0
            if current_stock > (predicted_demand * 1.5):
                status = "EXCESS"
                excess_qty = round(current_stock - predicted_demand, 1)
                message = f"Excess inventory detected: {excess_qty} kg above anticipated demand."
            else:
                status = "SUFFICIENT"
                message = "Stock levels are optimal and sufficient to satisfy demand."

        result = {
            "commodity": commodity,
            "region": region,
            "month": month,
            "beneficiary_count": beneficiary_count,
            "predicted_demand": predicted_demand,
            "current_stock": current_stock,
            "shortage": max(0.0, shortage),
            "status": status,
            "recommended_procurement": recommended_procurement,
            "message": message,
            "created_at": datetime.utcnow()
        }

        # Store prediction audit in MongoDB
        try:
            db = get_db()
            db.predictions.insert_one(result.copy())
            result.pop("_id", None)
        except Exception as e:
            logger.warning(f"Could not persist prediction audit: {e}")

        return result

    @classmethod
    def detect_anomaly(cls, transaction: dict) -> dict:
        """
        Executes Isolation Forest anomaly evaluation on a distribution transaction.
        Flags: NORMAL, SUSPICIOUS, or HIGH_RISK with transparent reasoning.
        """
        if cls._anomaly_model is None or cls._anomaly_scaler is None:
            cls.load_models()
            if cls._anomaly_model is None:
                # Fallback rule-based if model is unavailable
                return cls._rule_based_anomaly_check(transaction)

        quantity = float(transaction.get("quantity", 0.0))
        family_size = int(transaction.get("family_size", 4))
        card_type = transaction.get("card_type", "Priority (PHH)")
        commodity = transaction.get("commodity", "Rice")
        
        # Calculate standard entitlement quota
        if "AAY" in card_type:
            entitled_quota = 25.0 if commodity == "Rice" else (10.0 if commodity == "Wheat" else 2.0)
        elif "Priority" in card_type:
            entitled_quota = (family_size * 5.0) if commodity == "Rice" else ((family_size * 2.0) if commodity == "Wheat" else 1.0)
        else:
            entitled_quota = (family_size * 3.0) if commodity == "Rice" else ((family_size * 1.5) if commodity == "Wheat" else 1.0)

        quota_ratio = round(quantity / (entitled_quota + 1e-5), 3)
        days_since_prior = float(transaction.get("days_since_prior_txn", 25.0))
        monthly_frequency = int(transaction.get("monthly_frequency", 1))
        hour = int(transaction.get("hour", datetime.utcnow().hour))

        df_features = pd.DataFrame([{
            "quantity": quantity,
            "quantity_to_quota_ratio": quota_ratio,
            "days_since_prior_txn": days_since_prior,
            "monthly_frequency": monthly_frequency,
            "hour": hour
        }])

        scaled_features = cls._anomaly_scaler.transform(df_features)
        raw_score = float(cls._anomaly_model.decision_function(scaled_features)[0])
        is_outlier = int(cls._anomaly_model.predict(scaled_features)[0]) == -1

        # Determine risk level and generate understandable reasons
        reasons = []
        if quota_ratio > 2.0:
            reasons.append(f"Quantity ({quantity} kg) exceeds family quota entitlement ({entitled_quota} kg) by {quota_ratio:.1f}x")
        if days_since_prior < 2.0:
            reasons.append(f"Transaction occurred only {days_since_prior} days after previous collection")
        if monthly_frequency >= 4:
            reasons.append(f"High monthly collection frequency ({monthly_frequency} collections this month)")
        if hour < 7 or hour > 21:
            reasons.append(f"Distribution recorded at irregular off-hours ({hour}:00 hrs)")

        if is_outlier or quota_ratio >= 2.5 or days_since_prior < 1.0:
            status = "SUSPICIOUS"
            risk_level = "HIGH" if (quota_ratio >= 3.0 or raw_score < -0.10) else "MEDIUM"
            if not reasons:
                reasons.append("Unusually high statistical variance compared to historical cardholder pattern")
            reason_str = "; ".join(reasons)
        else:
            status = "NORMAL"
            risk_level = "LOW"
            reason_str = "Transaction conforms to cardholder entitlement quota and regular distribution schedule"

        return {
            "status": status,
            "risk_level": risk_level,
            "anomaly_score": round(raw_score, 4),
            "entitled_quota": entitled_quota,
            "quantity_to_quota_ratio": quota_ratio,
            "reason": reason_str,
            "requires_admin_review": (status == "SUSPICIOUS")
        }

    @classmethod
    def _rule_based_anomaly_check(cls, transaction: dict) -> dict:
        """Heuristic fallback when ML artifacts are loading."""
        qty = float(transaction.get("quantity", 0))
        if qty > 50:
            return {
                "status": "SUSPICIOUS",
                "risk_level": "HIGH",
                "anomaly_score": -0.35,
                "reason": "Unusually high quantity exceeding normal family distribution cap",
                "requires_admin_review": True
            }
        return {
            "status": "NORMAL",
            "risk_level": "LOW",
            "anomaly_score": 0.12,
            "reason": "Normal distribution",
            "requires_admin_review": False
        }


# Eager load models on import
MLService.load_models()
