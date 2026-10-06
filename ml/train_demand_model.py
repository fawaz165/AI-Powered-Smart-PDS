import json
import joblib
import sys
from pathlib import Path
import numpy as np

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from ml.preprocessing import prepare_train_test_data

SAVED_MODELS_DIR = Path(__file__).resolve().parent / "saved_models"
SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)


def train_and_evaluate_all():
    """
    Trains and compares 4 regression models on actual PDS demand data:
    1. Linear Regression
    2. Decision Tree Regressor
    3. Random Forest Regressor
    4. XGBoost Regressor
    
    Evaluates MAE, MSE, RMSE, R² on unseen test set.
    Selects the best model and serializes it using Joblib.
    """
    print("=" * 60)
    print("AI-POWERED SMART PDS - DEMAND PREDICTION MODEL BENCHMARK")
    print("=" * 60)
    
    data = prepare_train_test_data(test_size=0.20, random_state=42)
    X_train = data["X_train"]
    X_test = data["X_test"]
    y_train = data["y_train"]
    y_test = data["y_test"]
    preprocessor = data["preprocessor"]
    
    print(f"Training samples: {len(X_train)} | Testing samples: {len(X_test)}")
    print(f"Engineered feature vector dimension: {X_train.shape[1]}")
    print("-" * 60)
    
    candidate_models = {
        "Linear Regression": LinearRegression(),
        "Decision Tree": DecisionTreeRegressor(max_depth=8, random_state=42),
        "Random Forest": RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42),
        "XGBoost Regressor": XGBRegressor(n_estimators=120, learning_rate=0.08, max_depth=5, random_state=42)
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
        
        print(f" -> {name} Results: MAE: {mae:.2f} kg | RMSE: {rmse:.2f} kg | R²: {r2:.4f}")
        
        # Selection criterion: lowest test RMSE (and highest R²)
        if rmse < best_rmse:
            best_rmse = rmse
            best_model_name = name
            best_model_obj = model

    print("-" * 60)
    print(f"BEST MODEL SELECTED: {best_model_name} (RMSE: {best_rmse:.2f} kg, R²: {results[best_model_name]['R2']})")
    print("-" * 60)
    
    # Save best model and preprocessor
    best_model_path = SAVED_MODELS_DIR / "demand_model_best.joblib"
    preprocessor_path = SAVED_MODELS_DIR / "demand_preprocessor.joblib"
    metrics_path = SAVED_MODELS_DIR / "model_metrics.json"
    
    joblib.dump(best_model_obj, best_model_path)
    joblib.dump(preprocessor, preprocessor_path)
    
    final_payload = {
        "best_model": best_model_name,
        "best_model_file": str(best_model_path.name),
        "preprocessor_file": str(preprocessor_path.name),
        "evaluation_metrics": results
    }
    
    with open(metrics_path, "w") as f:
        json.dump(final_payload, f, indent=4)
        
    print(f"Saved best model artifact to: {best_model_path}")
    print(f"Saved preprocessor artifact to: {preprocessor_path}")
    print(f"Saved metrics summary to: {metrics_path}")
    
    return final_payload


if __name__ == "__main__":
    train_and_evaluate_all()
