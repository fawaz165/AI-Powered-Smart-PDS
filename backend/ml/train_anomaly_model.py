import sys
import json
import joblib
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score

# Ensure project root and backend are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
ML_DIR = Path(__file__).resolve().parent
for p in [str(PROJECT_ROOT), str(BACKEND_DIR), str(ML_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

SAVED_MODELS_DIR = Path(__file__).resolve().parent / "saved_models"
SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Dataset paths
RAW_FRAUD_CSV = Path(__file__).resolve().parent / "data" / "raw" / "fraud" / "Fraud Detection Dataset.csv"
BACKUP_TXNS_CSV = Path(__file__).resolve().parent / "data" / "generated_backup" / "pds_transactions.csv"
LEGACY_TXNS_CSV = Path(__file__).resolve().parent / "data" / "pds_transactions.csv"

KAGGLE_ANOMALY_FEATURE_COLS = [
    "Transaction_Amount",
    "Time_of_Transaction",
    "Previous_Fraudulent_Transactions",
    "Account_Age",
    "Number_of_Transactions_Last_24H"
]


def train_anomaly_models():
    """
    Trains Isolation Forest on the Kaggle Fraud Detection Dataset.
    Evaluates against actual labeled fraud patterns, benchmarks with LOF,
    and serializes the trained model and scaler.
    """
    print("=" * 65)
    print("AI-POWERED SMART PDS - KAGGLE FRAUD & ANOMALY MODEL TRAINING")
    print("=" * 65)
    
    if RAW_FRAUD_CSV.exists():
        df = pd.read_csv(RAW_FRAUD_CSV)
        print(f"Loaded Kaggle Fraud Detection Dataset: {len(df):,} transactions.")
        feature_cols = KAGGLE_ANOMALY_FEATURE_COLS
        has_ground_truth = "Fraudulent" in df.columns
        y_true = df["Fraudulent"].values if has_ground_truth else None
    elif BACKUP_TXNS_CSV.exists() or LEGACY_TXNS_CSV.exists():
        fallback_path = BACKUP_TXNS_CSV if BACKUP_TXNS_CSV.exists() else LEGACY_TXNS_CSV
        df = pd.read_csv(fallback_path)
        print(f"Loaded fallback transaction data: {len(df):,} records.")
        feature_cols = ["quantity", "quantity_to_quota_ratio", "days_since_prior_txn", "monthly_frequency", "hour"]
        has_ground_truth = "is_anomaly" in df.columns
        y_true = df["is_anomaly"].values if has_ground_truth else None
    else:
        raise FileNotFoundError(f"Fraud dataset not found at {RAW_FRAUD_CSV}")

    X_raw = df[feature_cols].copy()
    
    # Handle missing values if any
    imputer = SimpleImputer(strategy="median")
    X_imputed = imputer.fit_transform(X_raw)
    
    # Fit StandardScaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_imputed)
    
    # Train Isolation Forest
    # Contamination set to ~0.049 to match true Kaggle fraud rate
    iso_forest = IsolationForest(
        n_estimators=150,
        max_samples="auto",
        contamination=0.049,
        random_state=42
    )
    iso_forest.fit(X_scaled)
    
    # Evaluate score distribution
    scores = iso_forest.decision_function(X_scaled)
    preds = iso_forest.predict(X_scaled)  # -1 for anomaly, 1 for inlier
    binary_preds = np.where(preds == -1, 1, 0)
    
    num_flagged = int((preds == -1).sum())
    print(f"Isolation Forest flagged {num_flagged} of {len(df)} transactions ({num_flagged / len(df) * 100:.2f}%)")
    print(f"Score stats: Min: {scores.min():.4f}, Mean: {scores.mean():.4f}, Max: {scores.max():.4f}")
    
    # Supervised metrics if ground truth is present
    eval_metrics = {}
    if has_ground_truth and y_true is not None:
        prec = float(precision_score(y_true, binary_preds, zero_division=0))
        rec = float(recall_score(y_true, binary_preds, zero_division=0))
        f1 = float(f1_score(y_true, binary_preds, zero_division=0))
        try:
            auc = float(roc_auc_score(y_true, -scores))
        except Exception:
            auc = 0.5
        eval_metrics = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "roc_auc": round(auc, 4)
        }
        print(f"Evaluation against ground truth: Precision: {prec:.4f} | Recall: {rec:.4f} | F1: {f1:.4f} | ROC-AUC: {auc:.4f}")

    # Train LOF for comparative baseline on subset for fast performance
    sub_n = min(10000, len(X_scaled))
    lof = LocalOutlierFactor(n_neighbors=20, contamination=0.049, novelty=True)
    lof.fit(X_scaled[:sub_n])
    lof_preds = lof.predict(X_scaled[:sub_n])
    lof_flagged = int((lof_preds == -1).sum())
    print(f"LOF Baseline flagged: {lof_flagged} outliers in {sub_n} sample transactions")
    
    # Save Isolation Forest model and scaler
    model_file = SAVED_MODELS_DIR / "anomaly_model_isolation_forest.joblib"
    scaler_file = SAVED_MODELS_DIR / "anomaly_scaler.joblib"
    
    # Package imputer with scaler or save pipeline
    joblib.dump(iso_forest, model_file)
    joblib.dump({"scaler": scaler, "imputer": imputer, "features": feature_cols}, scaler_file)
    
    meta = {
        "dataset_source": "Kaggle Fraud Detection Dataset",
        "model_type": "IsolationForest",
        "contamination": 0.049,
        "features": feature_cols,
        "flagged_count": num_flagged,
        "total_evaluated": len(df),
        "score_threshold": float(np.percentile(scores, 5)),
        "metrics": eval_metrics
    }
    with open(SAVED_MODELS_DIR / "anomaly_metrics.json", "w") as f:
        json.dump(meta, f, indent=4)
        
    print(f"Saved Isolation Forest model to: {model_file}")
    print(f"Saved anomaly scaler artifact to: {scaler_file}")
    return meta


if __name__ == "__main__":
    train_anomaly_models()
