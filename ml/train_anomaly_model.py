import sys
import json
import joblib
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

# Ensure project root in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SAVED_MODELS_DIR = Path(__file__).resolve().parent / "saved_models"
SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)
DATA_PATH = Path(__file__).resolve().parent / "data" / "pds_transactions.csv"

ANOMALY_FEATURE_COLS = [
    "quantity",
    "quantity_to_quota_ratio",
    "days_since_prior_txn",
    "monthly_frequency",
    "hour"
]


def train_anomaly_models():
    """
    Trains Isolation Forest as primary anomaly detector for PDS transactions.
    Extracts behavioral features and saves the trained model and scaler.
    """
    print("=" * 60)
    print("AI-POWERED SMART PDS - ANOMALY DETECTION MODEL TRAINING")
    print("=" * 60)
    
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Transactions data not found at {DATA_PATH}")
        
    df = pd.read_csv(DATA_PATH)
    print(f"Loaded {len(df)} transaction records for anomaly modeling.")
    
    X = df[ANOMALY_FEATURE_COLS].copy()
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Train Isolation Forest
    # Contamination set to 0.04 (~4% expected outlier rate in PDS transactions)
    iso_forest = IsolationForest(
        n_estimators=150,
        max_samples="auto",
        contamination=0.04,
        random_state=42
    )
    iso_forest.fit(X_scaled)
    
    # Evaluate score distribution
    scores = iso_forest.decision_function(X_scaled)
    preds = iso_forest.predict(X_scaled)  # -1 for anomaly, 1 for inlier
    
    num_flagged = int((preds == -1).sum())
    print(f"Isolation Forest flagged {num_flagged} of {len(df)} transactions ({num_flagged / len(df) * 100:.2f}%)")
    print(f"Score stats: Min: {scores.min():.4f}, Mean: {scores.mean():.4f}, Max: {scores.max():.4f}")
    
    # Train LOF for comparative baseline
    lof = LocalOutlierFactor(n_neighbors=20, contamination=0.04, novelty=True)
    lof.fit(X_scaled)
    lof_preds = lof.predict(X_scaled)
    lof_flagged = int((lof_preds == -1).sum())
    print(f"LOF Baseline flagged: {lof_flagged} outliers")
    
    # Save Isolation Forest model and scaler
    model_file = SAVED_MODELS_DIR / "anomaly_model_isolation_forest.joblib"
    scaler_file = SAVED_MODELS_DIR / "anomaly_scaler.joblib"
    
    joblib.dump(iso_forest, model_file)
    joblib.dump(scaler, scaler_file)
    
    meta = {
        "model_type": "IsolationForest",
        "contamination": 0.04,
        "features": ANOMALY_FEATURE_COLS,
        "flagged_count": num_flagged,
        "total_evaluated": len(df),
        "score_threshold": float(np.percentile(scores, 4))
    }
    with open(SAVED_MODELS_DIR / "anomaly_metrics.json", "w") as f:
        json.dump(meta, f, indent=4)
        
    print(f"Saved Isolation Forest model to: {model_file}")
    print(f"Saved anomaly scaler to: {scaler_file}")
    return meta


if __name__ == "__main__":
    train_anomaly_models()
