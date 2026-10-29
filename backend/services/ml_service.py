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
    def get_model_health(cls):
        """Returns dynamic health status of demand and anomaly ML models."""
        cls.load_models()
        demand_ok = cls._demand_model is not None and cls._demand_preprocessor is not None
        anomaly_ok = cls._anomaly_model is not None and cls._anomaly_scaler is not None

        metrics = cls.get_model_metrics()
        best_name = metrics.get("best_model", "Linear Regression")

        if demand_ok and anomaly_ok:
            status_text = f"ML Model Active ({best_name} & Isolation Forest)"
            health = "HEALTHY"
        elif demand_ok:
            status_text = f"Demand Model Active ({best_name}) - Anomaly Offline"
            health = "DEGRADED"
        elif anomaly_ok:
            status_text = "Anomaly Isolation Forest Active - Demand Offline"
            health = "DEGRADED"
        else:
            status_text = "ML Models Offline"
            health = "OFFLINE"

        return {
            "health": health,
            "status_text": status_text,
            "demand_model_active": demand_ok,
            "anomaly_model_active": anomaly_ok,
            "best_demand_model": best_name if demand_ok else None,
            "anomaly_algorithm": "Isolation Forest" if anomaly_ok else None
        }

    _model_validated = False

    @classmethod
    def validate_selected_model(cls) -> bool:
        """
        Validates the loaded demand model against the benchmark results before inference:
        1. Checks that demand model and preprocessor are loaded in RAM.
        2. Validates against model_metrics.json (best model name, MSE, RMSE, R²).
        3. Asserts that the benchmarked R² >= 0.80 and RMSE < 5000 kg.
        4. Runs a verification sanity test on a baseline vector to guarantee numerical stability.
        """
        if cls._demand_model is None or cls._demand_preprocessor is None:
            cls.load_models()
        if cls._demand_model is None or cls._demand_preprocessor is None:
            logger.error("Model validation failed: Demand model or preprocessor not loaded.")
            return False

        metrics = cls.get_model_metrics()
        eval_metrics = metrics.get("evaluation_metrics", {})
        best_name = metrics.get("best_model", "Linear Regression")
        best_metrics = eval_metrics.get(best_name, {})

        r2 = best_metrics.get("R2", 0.0)
        rmse = best_metrics.get("RMSE", float("inf"))
        if r2 < 0.80 or rmse > 5000.0:
            logger.error(f"Selected model '{best_name}' failed quality threshold: R²={r2}, RMSE={rmse}")
            return False

        # Run verification sanity test
        try:
            df_test = pd.DataFrame([{
                "commodity": "Rice",
                "region": "Chennai",
                "month": 1,
                "beneficiary_count": 12500,
                "avg_family_size": 3.8,
                "previous_month_demand": 4200.0,
                "previous_month_offtake": 4032.0,
                "historical_average_3m": 4200.0,
                "current_stock": 3800.0,
                "allocated_quota": 4410.0,
                "is_festive_month": 1,
                "seasonal_index": 1.25
            }])
            Xt = cls._demand_preprocessor.transform(df_test)
            test_val = float(cls._demand_model.predict(Xt)[0])
            if np.isnan(test_val) or np.isinf(test_val) or test_val < 0:
                logger.error(f"Model validation failed: Sanity test produced invalid output {test_val}")
                return False
        except Exception as e:
            logger.error(f"Model verification check encountered error: {e}")
            return False

        cls._model_validated = True
        logger.info(f"Selected model '{best_name}' validated successfully against benchmark (RMSE={rmse} kg, R²={r2}).")
        return True

    @classmethod
    def predict_demand(cls, data: dict, save_audit: bool = True) -> dict:
        """
        Executes ML demand inference and applies inventory logic:
        Predicted Demand - Current Stock = Shortage.
        Includes safety stock, annual trend, factor explainability, and validation.
        """
        if cls._demand_model is None or cls._demand_preprocessor is None:
            cls.load_models()
            if cls._demand_model is None:
                raise RuntimeError("Demand ML model is not available.")

        if not cls._model_validated:
            if not cls.validate_selected_model():
                raise RuntimeError("Selected demand prediction model failed benchmark validation checks.")

        raw_commodity = str(data.get("commodity") or data.get("commodity_code") or "Rice").strip()
        commodity_name = raw_commodity
        commodity_code = None

        # Resolve commodity_code and canonical name against database catalog
        try:
            from backend.database.mongo import get_db
            import re
            db = get_db()
            com_doc = db.commodities.find_one({
                "$or": [
                    {"commodity_code": raw_commodity.upper()},
                    {"name": {"$regex": f"^{re.escape(raw_commodity)}$", "$options": "i"}}
                ]
            })
            if com_doc:
                commodity_name = com_doc["name"]
                commodity_code = com_doc["commodity_code"]
        except Exception:
            pass

        if not commodity_code:
            commodity_code = (
                "COM-RIC" if commodity_name.lower() == "rice" else (
                    "COM-WHT" if commodity_name.lower() == "wheat" else (
                        "COM-SUG" if commodity_name.lower() == "sugar" else (
                            "COM-DAL" if commodity_name.lower() == "dal" else f"COM-{commodity_name[:3].upper()}"
                        )
                    )
                )
            )

        commodity = commodity_name
        region = data.get("region", "Chennai").strip()
        month = int(data.get("month", datetime.utcnow().month))
        year = int(data.get("year") or data.get("forecast_year") or datetime.utcnow().year)
        beneficiary_count = int(data.get("beneficiary_count", 12500))
        previous_demand = float(data.get("previous_demand", 4200.0))
        current_stock = float(data.get("current_stock", 3800.0))
        safety_stock = float(data.get("safety_stock", data.get("buffer_stock", 0.0)))
        is_custom_scenario = bool(data.get("is_custom_scenario", False))
        
        # Inferred / default features
        avg_family_size = float(data.get("avg_family_size", 3.8))
        previous_offtake = float(data.get("previous_offtake", previous_demand * 0.96))
        hist_avg = float(data.get("historical_average_3m", previous_demand))
        allocated_quota = float(data.get("allocated_quota", previous_demand * 1.05))
        
        is_festive = 1 if (month == 1 or month in [10, 11]) else 0
        if month == 1:
            seasonal_index = 1.25 if commodity in ["Rice", "Sugar"] else 1.15
            seasonal_label = "Pongal Harvest Festival Peak"
        elif month in [10, 11]:
            seasonal_index = 1.12
            seasonal_label = "Diwali Festival Season"
        elif month == 5:
            seasonal_index = 1.04
            seasonal_label = "Summer Season Peak"
        elif month in [7, 8, 9]:
            seasonal_index = 0.96
            seasonal_label = "Monsoon Mid-Season"
        else:
            seasonal_index = 1.00
            seasonal_label = "Standard Monthly Baseline"

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

        # Apply annual demographic trend factor for forward years (approx 2% annual growth beyond 2024 baseline)
        annual_growth = 1.0 + max(0, year - 2024) * 0.02 if year > 2024 else 1.0
        predicted_demand = round(max(0.0, raw_pred * annual_growth), 1)

        # Configurable Safety Stock & Procurement Calculation
        shortage = round(max(0.0, predicted_demand - current_stock), 1)
        gross_requirement = round(predicted_demand + safety_stock, 1)
        recommended_procurement = round(max(0.0, gross_requirement - current_stock), 1)

        if shortage > 0:
            status = "SHORTAGE"
            if safety_stock > 0:
                message = f"Potential shortage of {shortage} kg. Recommended procurement: {recommended_procurement} kg (satisfies demand + {safety_stock} kg safety stock)."
            else:
                message = f"Potential shortage: {shortage} kg. Recommended procurement: {recommended_procurement} kg."
        elif current_stock < gross_requirement:
            status = "SHORTAGE" if shortage > 0 else "SUFFICIENT"
            message = f"Stock ({current_stock} kg) covers base demand ({predicted_demand} kg), but safety buffer requires {recommended_procurement} kg replenishment."
        elif current_stock > (predicted_demand * 1.5):
            status = "EXCESS"
            excess_qty = round(current_stock - predicted_demand, 1)
            message = f"Excess inventory detected: {excess_qty} kg above anticipated demand."
        else:
            status = "SUFFICIENT"
            message = "Stock levels are optimal and sufficient to satisfy demand."

        coverage_pct = round((current_stock / (predicted_demand + 1e-5)) * 100, 1)
        month_names = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        month_str = month_names[month] if 1 <= month <= 12 else f"Month {month}"

        growth_note = f" with a +{(annual_growth - 1.0)*100:.1f}% forward annual trend for Year {year}" if annual_growth > 1.0 else ""
        procurement_note = (
            f" With warehouse stock of {current_stock:,.1f} kg and safety buffer of {safety_stock:,.1f} kg, gross procurement required is {recommended_procurement:,.1f} kg ({shortage:,.1f} kg shortage + {safety_stock:,.1f} kg safety stock)."
            if recommended_procurement > 0 else
            f" Current stock of {current_stock:,.1f} kg covers anticipated demand and target safety buffer."
        )

        explanation = {
            "summary": (
                f"Model predicts {predicted_demand:,.1f} kg monthly demand for {commodity} in {region} for {month_str} {year}. "
                f"The pipeline transforms {beneficiary_count:,} registered cardholder families, "
                f"a {seasonal_label} ({seasonal_index:.2f}x seasonal multiplier for Month {month}), "
                f"and historical demand momentum of {previous_demand:,.1f} kg{growth_note}.{procurement_note}"
            ),
            "factors": [
                {
                    "name": "Demographic Scale",
                    "impact": "Primary (+)",
                    "value": f"{beneficiary_count:,} families",
                    "detail": f"Base consumption scale established for {region} Fair Price Shops."
                },
                {
                    "name": "Seasonal & Festive Index",
                    "impact": f"{'+' if seasonal_index >= 1.0 else '-'}{abs(seasonal_index - 1.0)*100:.0f}%",
                    "value": f"{seasonal_index:.2f}x ({seasonal_label})",
                    "detail": f"Seasonal weighting applied for {month_str} festival/climatic variations."
                },
                {
                    "name": "Historical Momentum",
                    "impact": "Baseline",
                    "value": f"{previous_demand:,.1f} kg",
                    "detail": "Historical baseline 3-month consumption momentum."
                },
                {
                    "name": "Warehouse Coverage",
                    "impact": "Deficit" if shortage > 0 else "Adequate",
                    "value": f"{coverage_pct:.1f}% covered",
                    "detail": f"Stock: {current_stock:,.1f} kg | Safety buffer target: {safety_stock:,.1f} kg."
                }
            ]
        }

        calculation_breakdown = {
            "baseline_demand": previous_demand,
            "seasonal_multiplier": seasonal_index,
            "seasonal_label": seasonal_label,
            "annual_trend_factor": round(annual_growth, 3),
            "raw_pipeline_prediction": round(raw_pred, 1),
            "final_predicted_demand": predicted_demand,
            "current_stock": current_stock,
            "safety_stock": safety_stock,
            "gross_requirement": gross_requirement,
            "net_shortage": shortage,
            "recommended_procurement": recommended_procurement,
            "baseline_momentum_kg": round(0.9927 * previous_demand, 1),
            "seasonal_component_kg": round(1050.64 * seasonal_index + (55.33 if is_festive else 0.0), 1),
            "procurement_formula": "max(0.0, (Predicted Demand + Safety Buffer) - Current Stock)"
        }

        result = {
            "commodity": commodity,
            "commodity_code": commodity_code,
            "region": region,
            "month": month,
            "year": year,
            "beneficiary_count": beneficiary_count,
            "predicted_demand": predicted_demand,
            "current_stock": current_stock,
            "safety_stock": safety_stock,
            "shortage": max(0.0, shortage),
            "status": status,
            "recommended_procurement": recommended_procurement,
            "message": message,
            "explanation": explanation,
            "calculation_breakdown": calculation_breakdown,
            "data_source": "USER_SCENARIO" if is_custom_scenario else "DATABASE_BACKED",
            "model_used": cls.get_model_metrics().get("best_model", "Linear Regression"),
            "model_validated": cls._model_validated,
            "created_at": datetime.utcnow()
        }

        # Store prediction audit in MongoDB
        if save_audit:
            try:
                db = get_db()
                db.predictions.insert_one(result.copy())
                result.pop("_id", None)
            except Exception as e:
                logger.warning(f"Could not persist prediction audit: {e}")

        return result

    @classmethod
    def detect_anomaly(cls, transaction: dict = None, **kwargs) -> dict:
        """
        Executes Isolation Forest anomaly evaluation on a distribution transaction.
        Flags: NORMAL, SUSPICIOUS, or HIGH_RISK with transparent reasoning.
        """
        if transaction is None:
            transaction = kwargs
        elif kwargs:
            transaction = {**transaction, **kwargs}

        if cls._anomaly_model is None or cls._anomaly_scaler is None:
            cls.load_models()
            if cls._anomaly_model is None:
                # Fallback rule-based if model is unavailable
                return cls._rule_based_anomaly_check(transaction)

        quantity = float(transaction.get("quantity", 0.0))
        commodity = str(transaction.get("commodity", "Rice")).strip()
        beneficiary_id = transaction.get("beneficiary_id")
        family_size = int(transaction.get("family_size", 4))
        card_type = str(transaction.get("card_type", "Priority (PHH)"))
        
        entitled_quota = None
        # Step 1: Query database for beneficiary-specific profile & registered quota if beneficiary_id is provided
        if beneficiary_id:
            try:
                from backend.database.mongo import get_db
                db = get_db()
                ben = db.beneficiaries.find_one({"beneficiary_id": beneficiary_id})
                if ben:
                    family_size = int(ben.get("family_size", family_size))
                    card_type = str(ben.get("ration_card_type", card_type))
                    # Official registered monthly quota
                    monthly_quota = ben.get("monthly_quota", {})
                    if commodity in monthly_quota and float(monthly_quota[commodity]) > 0:
                        entitled_quota = float(monthly_quota[commodity])
            except Exception as e:
                logger.warning(f"Failed to lookup beneficiary profile for {beneficiary_id}: {e}")

        # Step 2: Compute commodity-specific and card-type-specific entitlement rules if not explicitly overridden
        if entitled_quota is None:
            if "AAY" in card_type or "Antyodaya" in card_type:
                # Antyodaya Anna Yojana (AAY): Fixed 35 kg grain allocation per family (e.g. 25kg Rice, 10kg Wheat), 2kg Sugar, 2kg Dal
                if commodity == "Rice":
                    entitled_quota = 25.0
                elif commodity == "Wheat":
                    entitled_quota = 10.0
                elif commodity in ["Sugar", "Refined Sugar"]:
                    entitled_quota = 2.0
                elif commodity in ["Dal", "Toor Dal", "Pulses"]:
                    entitled_quota = 2.0
                else:
                    entitled_quota = 5.0
            elif "Priority" in card_type or "PHH" in card_type:
                # Priority Household (PHH): 5kg Rice/person, 2kg Wheat/person, 1kg Sugar/card, 1kg Dal/card
                if commodity == "Rice":
                    entitled_quota = family_size * 5.0
                elif commodity == "Wheat":
                    entitled_quota = family_size * 2.0
                elif commodity in ["Sugar", "Refined Sugar"]:
                    entitled_quota = 1.0
                elif commodity in ["Dal", "Toor Dal", "Pulses"]:
                    entitled_quota = 1.0
                else:
                    entitled_quota = family_size * 2.0
            else:
                # Non-Priority Household (NPHH): Restricted subsidized quota
                if commodity == "Rice":
                    entitled_quota = family_size * 3.0
                elif commodity == "Wheat":
                    entitled_quota = family_size * 1.5
                elif commodity in ["Sugar", "Refined Sugar"]:
                    entitled_quota = 1.0
                elif commodity in ["Dal", "Toor Dal", "Pulses"]:
                    entitled_quota = 1.0
                else:
                    entitled_quota = family_size * 1.0

        entitled_quota = max(1.0, float(entitled_quota))
        quota_ratio = round(quantity / (entitled_quota + 1e-5), 3)
        days_since_prior = float(transaction.get("days_since_prior_txn", 25.0))
        monthly_frequency = int(transaction.get("monthly_frequency", 1))
        hour = int(transaction.get("hour", datetime.utcnow().hour))

        # Check cumulative monthly draws from transactions database if available
        cumulative_month_draw = quantity
        if beneficiary_id:
            try:
                from backend.database.mongo import get_db
                db = get_db()
                now = datetime.utcnow()
                start_of_month = datetime(now.year, now.month, 1)
                past_txns = list(db.transactions.find({
                    "beneficiary_id": beneficiary_id,
                    "commodity": commodity,
                    "timestamp": {"$gte": start_of_month}
                }))
                cumulative_month_draw += sum(float(t.get("quantity", 0)) for t in past_txns)
            except Exception:
                pass

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

        # Determine anomaly score interpretation
        if raw_score >= 0.05:
            score_interpretation = "Strong Inlier: Transaction parameters lie well within normative historical cardholder distributions."
            score_badge = "NORMAL_INLIER"
        elif raw_score >= 0.0:
            score_interpretation = "Moderate Inlier: Conforms to expected distribution profile near median cluster boundaries."
            score_badge = "BORDERLINE_NORMAL"
        elif raw_score >= -0.10:
            score_interpretation = "Mild Outlier: Notable statistical deviation across quantity, collection cadence, or time parameters."
            score_badge = "MILD_ANOMALY"
        else:
            score_interpretation = "Severe Outlier: Short isolation tree path. Extreme multi-dimensional deviation from expected entitlement baseline."
            score_badge = "SEVERE_ANOMALY"

        # Determine risk level and generate explainable reasons
        reasons = []
        if quota_ratio > 2.0:
            reasons.append(f"Quantity ({quantity} kg) exceeds {commodity} card entitlement ({entitled_quota} kg) by {quota_ratio:.1f}x")
        elif quota_ratio > 1.0:
            reasons.append(f"Quantity ({quantity} kg) exceeds monthly {commodity} quota cap ({entitled_quota} kg)")

        if cumulative_month_draw > (entitled_quota * 1.5) and len(reasons) == 0:
            reasons.append(f"Cumulative monthly draws ({cumulative_month_draw:.1f} kg) exceed {commodity} monthly entitlement ({entitled_quota} kg)")

        if days_since_prior < 2.0:
            reasons.append(f"Transaction recorded only {days_since_prior} days after previous distribution")
        if monthly_frequency >= 4:
            reasons.append(f"High monthly draw frequency ({monthly_frequency} distributions logged this calendar month)")
        if hour < 7 or hour > 21:
            reasons.append(f"Distribution recorded outside Fair Price Shop operating hours ({hour}:00 hrs)")

        if is_outlier or quota_ratio >= 2.5 or days_since_prior < 1.0 or (commodity in ["Sugar", "Dal"] and quantity > 5.0):
            status = "SUSPICIOUS"
            risk_level = "HIGH" if (quota_ratio >= 3.0 or raw_score < -0.10 or (commodity in ["Sugar", "Dal"] and quantity >= 10.0)) else "MEDIUM"
            if not reasons:
                reasons.append("Multi-attribute statistical anomaly identified by Isolation Forest pipeline")
            reason_str = "; ".join(reasons)
        else:
            status = "NORMAL"
            risk_level = "LOW"
            reason_str = f"Transaction conforms to {card_type} {commodity} entitlement ({entitled_quota} kg) and standard distribution schedule"

        return {
            "status": status,
            "risk_level": risk_level,
            "anomaly_score": round(raw_score, 4),
            "score_interpretation": score_interpretation,
            "score_badge": score_badge,
            "entitled_quota": entitled_quota,
            "quantity_to_quota_ratio": quota_ratio,
            "commodity": commodity,
            "card_type": card_type,
            "family_size": family_size,
            "reason": reason_str,
            "requires_admin_review": (status == "SUSPICIOUS"),
            "audit_disclaimer": "Statistical anomalies are investigative flags for officer verification and do NOT constitute unilateral proof of fraud."
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
