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


def prepare_train_test_data(test_size=0.20, random_state=42):
    """
    Loads dataset, performs 80/20 train/test split, fits preprocessor on train only,
    and returns transformed X_train, X_test, y_train, y_test, and the preprocessor pipeline.
    """
    df = load_demand_dataset()
    
    feature_cols = CATEGORICAL_FEATURES + NUMERICAL_FEATURES
    X = df[feature_cols].copy()
    y = df[TARGET_COLUMN].values
    
    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )
    
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
