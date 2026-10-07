import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent

# Raw Kaggle Demand Data Paths
RAW_DEMAND_DIR = BASE_DIR / "data" / "raw" / "demand"
if not RAW_DEMAND_DIR.exists():
    RAW_DEMAND_DIR = ROOT_DIR / "ml" / "data" / "raw" / "demand"

TRAIN_CSV = RAW_DEMAND_DIR / "train.csv"
MEAL_CSV = RAW_DEMAND_DIR / "meal_info.csv"
CENTER_CSV = RAW_DEMAND_DIR / "fulfilment_center_info.csv"

# Fallback generated dataset
BACKUP_DEMAND_CSV = BASE_DIR / "data" / "generated_backup" / "pds_demand_data.csv"
LEGACY_DEMAND_CSV = BASE_DIR / "data" / "pds_demand_data.csv"

# Kaggle Food Demand Feature Definitions
CATEGORICAL_FEATURES = ["category", "cuisine", "center_type"]
NUMERICAL_FEATURES = [
    "week",
    "checkout_price",
    "base_price",
    "discount",
    "discount_pct",
    "emailer_for_promotion",
    "homepage_featured",
    "op_area",
    "city_code",
    "region_code"
]
TARGET_COLUMN = "num_orders"

# PDS Commodity to Kaggle Category & Cuisine Mapping
COMMODITY_MAPPING = {
    "Rice": {"category": "Rice Bowl", "cuisine": "Indian", "base_price": 285.0, "checkout_price": 260.0},
    "Wheat": {"category": "Sandwich", "cuisine": "Continental", "base_price": 220.0, "checkout_price": 195.0},
    "Sugar": {"category": "Desert", "cuisine": "Indian", "base_price": 180.0, "checkout_price": 165.0},
    "Dal": {"category": "Soup", "cuisine": "Indian", "base_price": 240.0, "checkout_price": 215.0}
}

# PDS Region to Kaggle Regional Center Mapping
REGION_MAPPING = {
    "Chennai": {"region_code": 56, "city_code": 590, "center_type": "TYPE_A", "op_area": 4.5},
    "Coimbatore": {"region_code": 85, "city_code": 526, "center_type": "TYPE_B", "op_area": 4.0},
    "Madurai": {"region_code": 34, "city_code": 614, "center_type": "TYPE_C", "op_area": 3.8},
    "Salem": {"region_code": 77, "city_code": 517, "center_type": "TYPE_A", "op_area": 3.5},
    "Tiruchirappalli": {"region_code": 92, "city_code": 679, "center_type": "TYPE_B", "op_area": 3.9}
}


def load_demand_dataset(sample_size=100000):
    """
    Loads and merges the Kaggle Food Demand Forecasting datasets:
    train.csv + meal_info.csv + fulfilment_center_info.csv.
    Falls back gracefully to historical PDS dataset if raw files are absent.
    """
    if TRAIN_CSV.exists() and MEAL_CSV.exists() and CENTER_CSV.exists():
        # Load Kaggle datasets
        if sample_size:
            train_df = pd.read_csv(TRAIN_CSV, nrows=sample_size)
        else:
            train_df = pd.read_csv(TRAIN_CSV)
            
        meal_df = pd.read_csv(MEAL_CSV)
        center_df = pd.read_csv(CENTER_CSV)

        # Merge on keys
        df = train_df.merge(center_df, on="center_id", how="left").merge(meal_df, on="meal_id", how="left")

        # Feature engineering
        df["discount"] = df["base_price"] - df["checkout_price"]
        df["discount_pct"] = df["discount"] / np.maximum(df["base_price"], 1.0)
        
        # Drop rows with nulls in required columns
        df = df.dropna(subset=CATEGORICAL_FEATURES + NUMERICAL_FEATURES + [TARGET_COLUMN])
        return df

    # Fallback to generated backup if needed
    for fallback_path in [BACKUP_DEMAND_CSV, LEGACY_DEMAND_CSV]:
        if fallback_path.exists():
            return pd.read_csv(fallback_path)

    raise FileNotFoundError(f"Neither Kaggle raw demand files nor fallback CSV found at {RAW_DEMAND_DIR}")


def build_preprocessor():
    """Builds scikit-learn ColumnTransformer for categorical and numerical features."""
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
            ("num", StandardScaler(), NUMERICAL_FEATURES)
        ],
        remainder="drop"
    )
    return preprocessor


def prepare_train_test_data(sample_size=100000, test_size=0.20, random_state=42):
    """
    Loads Kaggle Food Demand dataset, performs 80/20 train/test split,
    fits ColumnTransformer on train only, and returns transformed datasets.
    """
    df = load_demand_dataset(sample_size=sample_size)
    
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


def convert_pds_to_kaggle_demand_features(pds_data: dict) -> pd.DataFrame:
    """
    Adapts PDS input parameters into the exact feature representation
    expected by the trained Kaggle Food Demand preprocessor.
    """
    commodity = pds_data.get("commodity", "Rice")
    region = pds_data.get("region", "Chennai")
    month = int(pds_data.get("month", 10))
    is_festive = 1 if (month == 1 or month in [10, 11] or pds_data.get("is_festive_month")) else 0
    
    com_info = COMMODITY_MAPPING.get(commodity, COMMODITY_MAPPING["Rice"])
    reg_info = REGION_MAPPING.get(region, REGION_MAPPING["Chennai"])
    
    # Week calculation from month (approx 4 weeks per month)
    week = min(max(1, (month * 4) - 2), 145)
    
    base_price = com_info["base_price"]
    checkout_price = com_info["checkout_price"]
    if is_festive:
        # Festive subsidy / discount in PDS
        checkout_price = round(base_price * 0.85, 2)
        emailer = 1
        homepage = 1
    else:
        emailer = 0
        homepage = 0
        
    discount = base_price - checkout_price
    discount_pct = discount / max(base_price, 1.0)
    
    df_row = pd.DataFrame([{
        "category": com_info["category"],
        "cuisine": com_info["cuisine"],
        "center_type": reg_info["center_type"],
        "week": week,
        "checkout_price": checkout_price,
        "base_price": base_price,
        "discount": discount,
        "discount_pct": discount_pct,
        "emailer_for_promotion": emailer,
        "homepage_featured": homepage,
        "op_area": reg_info["op_area"],
        "city_code": reg_info["city_code"],
        "region_code": reg_info["region_code"]
    }])
    return df_row
