import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "pds_demand_data.csv"

# Selected Feature Columns (No target leakage)
CATEGORICAL_FEATURES = ["commodity", "region"]
NUMERICAL_FEATURES = [
    "month",
    "beneficiary_count",
    "avg_family_size",
    "previous_month_demand",
    "previous_month_offtake",
    "historical_average_3m",
    "current_stock",
    "allocated_quota",
    "is_festive_month",
    "seasonal_index"
]
TARGET_COLUMN = "monthly_demand"


def load_demand_dataset(csv_path=None):
    """Loads and validates the historical PDS demand dataset."""
    path = csv_path or DATA_PATH
    if not Path(path).exists():
        raise FileNotFoundError(f"Demand dataset not found at {path}")
    df = pd.read_csv(path)
    
    # Drop rows with nulls if any
    df = df.dropna(subset=CATEGORICAL_FEATURES + NUMERICAL_FEATURES + [TARGET_COLUMN])
    return df


def build_preprocessor():
    """Builds a scikit-learn ColumnTransformer for categorical and numerical features."""
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
            ("num", StandardScaler(), NUMERICAL_FEATURES)
        ],
        remainder="drop"
    )
    return preprocessor


def prepare_train_test_data(test_size=0.20, chronological=True, random_state=42):
    """
    Loads dataset, performs month-grouped chronological train/test split (or random if chronological=False),
    ensuring that all districts and commodities belonging to the same monthly period remain in the same partition.
    Fits preprocessor strictly on the training partition only to prevent data leakage,
    and returns transformed X_train, X_test, y_train, y_test, raw subsets, and the preprocessor pipeline.
    """
    df = load_demand_dataset()
    feature_cols = CATEGORICAL_FEATURES + NUMERICAL_FEATURES

    if chronological:
        # Group-based chronological split by date so no monthly period is split across train and test
        if "date" in df.columns:
            df["_sort_dt"] = pd.to_datetime(df["date"])
            df = df.sort_values(["_sort_dt", "region", "commodity"]).reset_index(drop=True)
            unique_periods = df["_sort_dt"].drop_duplicates().sort_values().tolist()
            n_train_periods = int(len(unique_periods) * (1.0 - test_size))
            train_periods = set(unique_periods[:n_train_periods])
            
            is_train = df["_sort_dt"].isin(train_periods)
            X_train_raw = df.loc[is_train, feature_cols].copy().reset_index(drop=True)
            X_test_raw = df.loc[~is_train, feature_cols].copy().reset_index(drop=True)
            y_train = df.loc[is_train, TARGET_COLUMN].values
            y_test = df.loc[~is_train, TARGET_COLUMN].values
            df = df.drop(columns=["_sort_dt"])
        elif "year" in df.columns and "month" in df.columns:
            df = df.sort_values(["year", "month", "region", "commodity"]).reset_index(drop=True)
            periods = df[["year", "month"]].drop_duplicates().values.tolist()
            n_train_periods = int(len(periods) * (1.0 - test_size))
            train_periods = set((p[0], p[1]) for p in periods[:n_train_periods])
            
            is_train = df.apply(lambda r: (r["year"], r["month"]) in train_periods, axis=1)
            X_train_raw = df.loc[is_train, feature_cols].copy().reset_index(drop=True)
            X_test_raw = df.loc[~is_train, feature_cols].copy().reset_index(drop=True)
            y_train = df.loc[is_train, TARGET_COLUMN].values
            y_test = df.loc[~is_train, TARGET_COLUMN].values
        else:
            split_idx = int(len(df) * (1.0 - test_size))
            X = df[feature_cols].copy()
            y = df[TARGET_COLUMN].values
            X_train_raw = X.iloc[:split_idx].copy()
            X_test_raw = X.iloc[split_idx:].copy()
            y_train = y[:split_idx]
            y_test = y[split_idx:]
    else:
        X = df[feature_cols].copy()
        y = df[TARGET_COLUMN].values
        X_train_raw, X_test_raw, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )

    # Fit preprocessor strictly on train set to prevent feature/scale leakage
    preprocessor = build_preprocessor()
    X_train = preprocessor.fit_transform(X_train_raw)
    X_test = preprocessor.transform(X_test_raw)

    return {
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "X_train_raw": X_train_raw,
        "X_test_raw": X_test_raw,
        "preprocessor": preprocessor,
        "feature_names": preprocessor.get_feature_names_out().tolist()
    }
