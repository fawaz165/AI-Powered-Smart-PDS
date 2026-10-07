import json
import joblib
import sys
from pathlib import Path
import numpy as np

# Ensure project root, backend, and ml are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
ML_DIR = Path(__file__).resolve().parent
for p in [str(PROJECT_ROOT), str(BACKEND_DIR), str(ML_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

try:
    from backend.ml.preprocessing import prepare_train_test_data
except ImportError:
    from ml.preprocessing import prepare_train_test_data

SAVED_MODELS_DIR = Path(__file__).resolve().parent / "saved_models"
SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)


def train_and_evaluate_all():
    """
    Trains and benchmarks 4 regression models on Kaggle Food Demand Forecasting data:
    1. Linear Regression
    2. Decision Tree Regressor
    3. Random Forest Regressor
    4. XGBoost Regressor
    
    Evaluates MAE, MSE, RMSE, R² on unseen test set.
    Selects the best model and serializes it using Joblib.
    """
    print("=" * 65)
    print("AI-POWERED SMART PDS - KAGGLE FOOD DEMAND MODEL BENCHMARK")
    print("=" * 65)
    
    data = prepare_train_test_data(sample_size=60000, test_size=0.20, random_state=42)
    X_train = data["X_train"]
    X_test = data["X_test"]
    y_train = data["y_train"]
    y_test = data["y_test"]
    preprocessor = data["preprocessor"]
    
    print(f"Training samples: {len(X_train):,} | Testing samples: {len(X_test):,}")
    print(f"Engineered feature vector dimension: {X_train.shape[1]}")
    print("-" * 65)
    
    candidate_models = {
        "Linear Regression": LinearRegression(),
        "Decision Tree": DecisionTreeRegressor(max_depth=10, random_state=42),
        "Random Forest": RandomForestRegressor(n_estimators=50, max_depth=12, n_jobs=-1, random_state=42),
        "XGBoost Regressor": XGBRegressor(n_estimators=100, learning_rate=0.10, max_depth=6, random_state=42)
    }
    
    results = {}
    best_model_name = None
    best_rmse = float("inf")
    best_model_obj = None
    
    for name, model in candidate_models.items():
        print(f"Training {name}...")
        model.fit(X_train, y_train)
        
        preds = model.predict(X_test)
        
        mae = float(mean_absolute_error(y_test, preds))
        mse = float(mean_squared_error(y_test, preds))
        rmse = float(np.sqrt(mse))
        r2 = float(r2_score(y_test, preds))
        
        results[name] = {
            "MAE": round(mae, 2),
            "MSE": round(mse, 2),
            "RMSE": round(rmse, 2),
            "R2": round(r2, 4)
        }
        
        print(f" -> {name} Results: MAE: {mae:.2f} | RMSE: {rmse:.2f} | R²: {r2:.4f}")
        
        # Selection criterion: lowest test RMSE (and highest R²)
        if rmse < best_rmse:
            best_rmse = rmse
            best_model_name = name
            best_model_obj = model

    print("-" * 65)
    print(f"BEST MODEL SELECTED: {best_model_name} (RMSE: {best_rmse:.2f}, R²: {results[best_model_name]['R2']})")
    print("-" * 65)
    
    # Save best model and preprocessor
    best_model_path = SAVED_MODELS_DIR / "demand_model_best.joblib"
    preprocessor_path = SAVED_MODELS_DIR / "demand_preprocessor.joblib"
    
    joblib.dump(best_model_obj, best_model_path)
    joblib.dump(preprocessor, preprocessor_path)
    
    metrics_payload = {
        "dataset_source": "Kaggle Food Demand Forecasting",
        "training_samples": len(X_train),
        "testing_samples": len(X_test),
        "best_model": best_model_name,
        "best_model_file": "demand_model_best.joblib",
        "preprocessor_file": "demand_preprocessor.joblib",
        "evaluation_metrics": results
    }
    
    with open(SAVED_MODELS_DIR / "model_metrics.json", "w") as f:
        json.dump(metrics_payload, f, indent=4)
        
    print(f"Saved best model ({best_model_name}) to: {best_model_path}")
    print(f"Saved preprocessor to: {preprocessor_path}")
    print(f"Saved metrics benchmark to: {SAVED_MODELS_DIR / 'model_metrics.json'}")
    return metrics_payload


if __name__ == "__main__":
    train_and_evaluate_all()
