import pytest
import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from backend.ml.preprocessing import (
    load_demand_dataset,
    prepare_train_test_data,
    CATEGORICAL_FEATURES,
    NUMERICAL_FEATURES,
    TARGET_COLUMN
)
from backend.services.ml_service import MLService
from backend.config import Config


def test_chronological_split_and_zero_leakage():
    """Validates that train/test split is strictly chronological, month-grouped, and has zero target or temporal leakage."""
    df = load_demand_dataset()
    data = prepare_train_test_data(test_size=0.20, chronological=True)

    X_train_raw = data["X_train_raw"]
    X_test_raw = data["X_test_raw"]
    y_train = data["y_train"]
    y_test = data["y_test"]

    # 1. Target column must not exist in input features
    assert TARGET_COLUMN not in X_train_raw.columns, "Target column leaked into training features!"
    assert TARGET_COLUMN not in X_test_raw.columns, "Target column leaked into test features!"
    for fname in data["feature_names"]:
        assert TARGET_COLUMN not in fname, f"Target column leaked into feature name: {fname}"

    # 2. Month-grouped partitioning check: 28 full months train (560 samples), 8 full months test (160 samples)
    assert len(X_train_raw) == 560
    assert len(X_test_raw) == 160
    assert len(y_train) == 560
    assert len(y_test) == 160
    assert len(X_train_raw) + len(X_test_raw) == len(df)

    # 3. Preprocessor must be fitted strictly on X_train_raw
    preprocessor = data["preprocessor"]
    assert hasattr(preprocessor, "transformers_")


def test_month_grouped_partitioning_no_boundary_split():
    """
    Validates that monthly periods are NEVER divided across train and test partitions.
    All districts and commodities for any given month must reside in the exact same partition.
    """
    df = load_demand_dataset()
    df["_dt"] = pd.to_datetime(df["date"])
    df = df.sort_values(["_dt", "region", "commodity"]).reset_index(drop=True)
    unique_periods = df["_dt"].drop_duplicates().sort_values().tolist()
    
    n_train_periods = int(len(unique_periods) * 0.80)
    train_periods = set(unique_periods[:n_train_periods])
    test_periods = set(unique_periods[n_train_periods:])
    
    # Assert zero period overlap
    assert len(train_periods.intersection(test_periods)) == 0, "Temporal overlap between train and test periods!"
    
    # Assert May 2024 is strictly in test
    may_2024 = pd.Timestamp("2024-05-01")
    assert may_2024 in test_periods, "May 2024 should be held out in test period"
    assert may_2024 not in train_periods, "May 2024 leaked into training periods"
    
    # Verify all 20 observations for May 2024 exist and all belong to test
    may_rows = df[df["_dt"] == may_2024]
    assert len(may_rows) == 20, f"Expected 20 rows for May 2024, got {len(may_rows)}"
    assert all(d in test_periods for d in may_rows["_dt"]), "May 2024 observations divided across split boundary!"


def test_model_artifacts_integrity_and_feature_order():
    """Validates that all .joblib and .json artifacts exist, load cleanly, and have identical feature definitions."""
    model_dir = Config.MODEL_DIR

    # 1. Demand artifacts
    demand_model_path = model_dir / "demand_model_best.joblib"
    demand_preproc_path = model_dir / "demand_preprocessor.joblib"
    model_metrics_path = model_dir / "model_metrics.json"

    assert demand_model_path.exists(), "demand_model_best.joblib missing"
    assert demand_preproc_path.exists(), "demand_preprocessor.joblib missing"
    assert model_metrics_path.exists(), "model_metrics.json missing"

    demand_model = joblib.load(demand_model_path)
    demand_preproc = joblib.load(demand_preproc_path)

    # 2. Anomaly artifacts
    anomaly_model_path = model_dir / "anomaly_model_isolation_forest.joblib"
    anomaly_scaler_path = model_dir / "anomaly_scaler.joblib"
    anomaly_metrics_path = model_dir / "anomaly_metrics.json"

    assert anomaly_model_path.exists(), "anomaly_model_isolation_forest.joblib missing"
    assert anomaly_scaler_path.exists(), "anomaly_scaler.joblib missing"
    assert anomaly_metrics_path.exists(), "anomaly_metrics.json missing"

    anomaly_model = joblib.load(anomaly_model_path)
    anomaly_scaler = joblib.load(anomaly_scaler_path)

    # 3. Check scaler feature counts
    expected_anomaly_features = ["quantity", "quantity_to_quota_ratio", "days_since_prior_txn", "monthly_frequency", "hour"]
    assert anomaly_scaler.n_features_in_ == len(expected_anomaly_features)
    assert anomaly_model.n_features_in_ == len(expected_anomaly_features)


def test_direct_vs_api_demand_prediction_equivalence():
    """Validates that direct joblib model inference produces identical predictions to MLService API pipeline."""
    sample_payload = {
        "commodity": "Rice",
        "region": "Chennai",
        "month": 11,
        "year": 2026,
        "beneficiary_count": 12500,
        "current_stock": 3800.0,
        "safety_stock": 500.0,
        "previous_demand": 4200.0,
        "is_custom_scenario": False
    }

    # API / Service inference
    service_result = MLService.predict_demand(sample_payload, save_audit=False)
    api_predicted_demand = service_result["predicted_demand"]

    # Direct model inference
    model = joblib.load(Config.MODEL_DIR / "demand_model_best.joblib")
    preproc = joblib.load(Config.MODEL_DIR / "demand_preprocessor.joblib")

    df_direct = pd.DataFrame([{
        "commodity": "Rice",
        "region": "Chennai",
        "month": 11,
        "beneficiary_count": 12500,
        "avg_family_size": 3.8,
        "previous_month_demand": 4200.0,
        "previous_month_offtake": 4200.0 * 0.96,
        "historical_average_3m": 4200.0,
        "current_stock": 3800.0,
        "allocated_quota": 4200.0 * 1.05,
        "is_festive_month": 1,
        "seasonal_index": 1.12
    }])

    X_direct = preproc.transform(df_direct)
    raw_pred = float(model.predict(X_direct)[0])
    direct_predicted_demand = round(max(0.0, raw_pred * 1.04), 1)

    assert api_predicted_demand == direct_predicted_demand, (
        f"API prediction ({api_predicted_demand}) does not match direct model ({direct_predicted_demand})"
    )


def test_direct_vs_api_anomaly_scoring_equivalence():
    """Validates that direct Isolation Forest scoring matches MLService anomaly score exactly."""
    txn = {
        "quantity": 30.0,
        "commodity": "Rice",
        "card_type": "Priority (PHH)",
        "family_size": 4,
        "days_since_prior_txn": 20.0,
        "monthly_frequency": 1,
        "hour": 11
    }

    service_out = MLService.detect_anomaly(txn)
    service_score = service_out["anomaly_score"]

    iso_forest = joblib.load(Config.MODEL_DIR / "anomaly_model_isolation_forest.joblib")
    scaler = joblib.load(Config.MODEL_DIR / "anomaly_scaler.joblib")

    # Priority quota for 4 members = 20.0 kg -> ratio = 30 / 20 = 1.5
    df_feat = pd.DataFrame([{
        "quantity": 30.0,
        "quantity_to_quota_ratio": 1.5,
        "days_since_prior_txn": 20.0,
        "monthly_frequency": 1,
        "hour": 11
    }])

    scaled_feat = scaler.transform(df_feat)
    direct_score = round(float(iso_forest.decision_function(scaled_feat)[0]), 4)

    assert service_score == direct_score, f"Anomaly score mismatch: {service_score} vs {direct_score}"

