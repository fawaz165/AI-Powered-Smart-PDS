# AI-Powered Smart Public Distribution System (PDS)

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Flask 3.1](https://img.shields.io/badge/Flask-3.1-black.svg)](https://flask.palletsprojects.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-6.0-green.svg)](https://www.mongodb.com/)
[![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-1.9-orange.svg)](https://scikit-learn.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-3.2-red.svg)](https://xgboost.readthedocs.io/)
[![Pytest](https://img.shields.io/badge/Tests-14%20Passed-brightgreen.svg)](https://pytest.org/)

An enterprise-grade, full-stack AI/ML-driven solution designed to replace traditional manual food-grain estimation in the Public Distribution System (PDS) with data-driven predictive intelligence.

---

## 1. Project Objective & Core Functions

The system implements three major intelligent pillars under the **National Food Security Act (NFSA)** and **Targeted Public Distribution System (TPDS)** framework:

### 1. ML Demand Prediction
- Predicts monthly demand for essential commodities: **Rice, Wheat, Sugar, Dal**.
- Evaluates 4 machine learning regressors:
  1. **Linear Regression**
  2. **Decision Tree Regressor**
  3. **Random Forest Regressor**
  4. **XGBoost Regressor**
- Calculates genuine evaluation metrics (**MAE, MSE, RMSE, R²**) without hardcoding or fabricating results.
- Serializes and eagerly loads the best model via **Joblib** during Flask API startup.

### 2. Fraud & Anomaly Detection
- Analyzes distribution transactions using unsupervised **Isolation Forest** and **Local Outlier Factor (LOF)**.
- Flags transactions into three risk categories: `NORMAL`, `SUSPICIOUS`, and `HIGH RISK`.
- **Ethical AI Guardrail**: Anomalies are flagged for administrator audit and are **not** automatically branded as fraud without officer verification.
- Generates human-readable, explainable reasons (e.g., *"Quantity exceeds family quota entitlement by 4.2x within 2 days of prior collection"*).

### 3. Intelligent Inventory Management
- Continuously compares forecasted demand with current warehouse inventory.
- Detects critical stock shortages, buffer deficits, and excessive inventory.
- Implements the exact procurement logic:
  $$\text{Shortage} = \text{Predicted Demand} - \text{Current Stock}$$
  $$\text{If Shortage} > 0 \implies \text{Status} = \text{"SHORTAGE"}, \quad \text{Recommended Procurement} = \text{Shortage}$$
  $$\text{If Shortage} \le 0 \implies \text{Status} = \text{"SUFFICIENT"}, \quad \text{Recommended Procurement} = 0$$

### 4. Thread-Safe Concurrency
- Uses Python's `threading.Lock` inside `InventoryService` to serialize multi-beneficiary distributions.
- Prevents race conditions and negative inventory (e.g., initial 100 kg stock with concurrent 30 kg and 40 kg draws correctly results in exactly 30 kg remaining).

---

## 2. Technology Stack

| Layer | Technologies |
|---|---|
| **Backend API** | Python 3.11+, Flask 3.1.3, Flask-CORS, PyMongo |
| **Database** | MongoDB Server (Indexed collections: `users`, `beneficiaries`, `commodities`, `inventory`, `transactions`, `predictions`, `fraud_alerts`, `ration_shops`) |
| **Machine Learning** | Pandas 3.0, NumPy 2.0, Scikit-learn 1.9, XGBoost 3.2, Joblib |
| **Frontend UI** | HTML5, Modern CSS3 (Glassmorphic Dark Design System), Vanilla JS, Chart.js, FontAwesome |
| **Reporting** | OpenPyXL, Pandas ExcelWriter |
| **DevOps & CI/CD** | Docker, Docker Compose, GitHub Actions |
| **Testing** | Pytest 9.1 (14 automated test cases covering health, CRUD, concurrency, and ML inference) |

---

## 3. Project Directory Structure

```
AI-Powered Smart PDS/
├── backend/
│   ├── app.py                      # Flask factory & blueprint registration
│   ├── config.py                   # Environment configuration & thresholds
│   ├── requirements.txt            # Python dependencies
│   ├── database/
│   │   ├── mongo.py                # MongoDB singleton & index manager
│   │   └── seed_db.py              # Initial database seeding script
│   ├── models/                     # Schemas (User, Beneficiary, Commodity, Inventory, Txn)
│   ├── routes/                     # REST blueprints (auth, beneficiaries, commodities, inventory, txns, ml, reports)
│   ├── services/                   # Business logic (Auth, ML inference, Thread-safe inventory, Reports)
│   ├── utils/                      # Logging & input validators
│   └── ml/
│       ├── data/
│       │   ├── generate_pds_data.py    # Realistic TPDS/NFSA dataset generator
│       │   ├── pds_demand_data.csv     # 720 records across 5 districts (2022-2024)
│       │   └── pds_transactions.csv    # 2,500 transaction distribution logs
│       ├── preprocessing.py            # ColumnTransformer, OneHotEncoder, StandardScaler
│       ├── train_demand_model.py       # Trains & benchmarks 4 regression models
│       ├── train_anomaly_model.py      # Trains Isolation Forest anomaly detector
│       └── saved_models/
│           ├── demand_model_best.joblib
│           ├── demand_preprocessor.joblib
│           ├── anomaly_model_isolation_forest.joblib
│           ├── anomaly_scaler.joblib
│           └── model_metrics.json      # Genuine evaluation metrics
├── frontend/
│   ├── index.html                  # Login & authentication portal
│   ├── dashboard.html              # Executive operational dashboard with Chart.js
│   ├── beneficiaries.html          # Cardholder directory & CRUD modal
│   ├── commodities.html            # Food-grain catalog & subsidized pricing
│   ├── inventory.html              # Regional stock, shortage alerts & procurement
│   ├── transactions.html           # Live distribution ledger with thread-safe modal
│   ├── predictions.html            # Interactive ML demand forecaster
│   ├── fraud.html                  # Anomaly review console & live scanner
│   ├── reports.html                # One-click Excel spreadsheet export
│   ├── about.html                  # Technical architecture & Viva presentation guide
│   ├── css/style.css               # Ultra-modern glassmorphic design system
│   └── js/                         # API client, charts, and controllers
├── tests/                          # 14 comprehensive Pytest test cases
├── Dockerfile                      # Production multi-stage Dockerfile
├── docker-compose.yml              # Containerized Mongo + Web orchestration
├── .github/workflows/ci-cd.yml     # Automated CI/CD test, build & push workflow
├── .env.example
└── README.md
```

---

## 4. Machine Learning Model Benchmark

Models were trained on 80% split and tested on 20% unseen test data:

| Algorithm | MAE (kg) | MSE | RMSE (kg) | $R^2$ Score | Production Status |
|---|---|---|---|---|---|
| **Linear Regression** | **289.22** | **166,283.48** | **407.78** | **0.9994** | **Selected & Active** |
| Random Forest Regressor | 373.90 | 358,789.09 | 598.99 | 0.9986 | Benchmarked |
| XGBoost Regressor | 390.63 | 361,767.87 | 601.47 | 0.9986 | Benchmarked |
| Decision Tree Regressor | 479.07 | 575,524.12 | 758.63 | 0.9978 | Benchmarked |

*Metrics are stored in `ml/saved_models/model_metrics.json` and dynamically rendered in the frontend.*

---

## 5. Quick Start & Execution

### Option A: Local Execution (Python + MongoDB)

1. **Verify MongoDB is running** on `localhost:27017`.
2. **Install dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. **Generate datasets and train ML models**:
   ```bash
   python backend/ml/data/generate_pds_data.py
   python backend/ml/train_demand_model.py
   python backend/ml/train_anomaly_model.py
   ```
4. **Seed database with initial records**:
   ```bash
   python backend/database/seed_db.py
   ```
5. **Run the Flask Web Server**:
   ```bash
   python backend/app.py
   ```
6. **Open in browser**:
   Navigate to [http://localhost:5000](http://localhost:5000)  
   *Default Credentials:* Username: `admin` | Password: `admin123`

---

### Option B: Docker Compose

Run the entire stack with a single command:
```bash
docker compose up --build
```
The application will be accessible at [http://localhost:5000](http://localhost:5000).

---

## 6. Running the Test Suite

Execute the automated test suite using `pytest`:
```bash
pytest tests/ -v
```

Expected output:
```
tests/test_anomaly_detection.py::test_detect_anomaly_normal_transaction PASSED
tests/test_anomaly_detection.py::test_detect_anomaly_suspicious_bulk_excess PASSED
tests/test_auth.py::test_auth_success PASSED
tests/test_auth.py::test_auth_invalid_credentials PASSED
tests/test_auth.py::test_auth_me_endpoint_with_token PASSED
tests/test_crud_apis.py::test_beneficiary_crud PASSED
tests/test_crud_apis.py::test_commodity_crud PASSED
tests/test_crud_apis.py::test_inventory_alerts_endpoint PASSED
tests/test_demand_prediction.py::test_predict_demand_api_shortage_calculation PASSED
tests/test_demand_prediction.py::test_predict_demand_api_sufficient_stock PASSED
tests/test_health.py::test_health_check PASSED
tests/test_health.py::test_database_connection PASSED
tests/test_thread_safe_inventory.py::test_thread_safe_inventory_example_scenario PASSED
tests/test_thread_safe_inventory.py::test_thread_safe_negative_stock_rejection PASSED
======================= 14 passed in 13.42s =======================
```

---

## 7. Core REST API Endpoints

### Health Check
- `GET /api/health` &rarr; `{"status": "healthy", "service": "...", "version": "1.0.0"}`

### Authentication
- `POST /api/auth/login` &rarr; Authenticates user and returns signed Bearer token.
- `GET /api/auth/me` &rarr; Returns authenticated user profile.

### Machine Learning
- `POST /api/predict-demand` &rarr; Predicts demand, computes shortage, and provides procurement recommendation.
  ```json
  // Request
  {
    "commodity": "Rice",
    "region": "Chennai",
    "beneficiary_count": 12500,
    "previous_demand": 4200,
    "current_stock": 3800,
    "month": 11
  }
  // Response
  {
    "status": "success",
    "data": {
      "commodity": "Rice",
      "predicted_demand": 4617.8,
      "current_stock": 3800.0,
      "shortage": 817.8,
      "recommended_procurement": 817.8,
      "status": "SHORTAGE",
      "message": "Potential shortage: 817.8 kg. Recommended procurement: 817.8 kg."
    }
  }
  ```
- `POST /api/detect-anomaly` &rarr; Evaluates transaction risk using Isolation Forest.
- `GET /api/model-metrics` &rarr; Returns benchmark metrics (MAE, MSE, RMSE, R²).

### CRUD & Operations
- `GET /api/beneficiaries`, `POST /api/beneficiaries`, `GET /api/beneficiaries/<id>`, `PUT /api/beneficiaries/<id>`, `DELETE /api/beneficiaries/<id>`
- `GET /api/commodities`, `POST /api/commodities`
- `GET /api/inventory`, `GET /api/inventory/alerts`, `PUT /api/inventory/update-stock`
- `GET /api/transactions`, `POST /api/transactions` (Thread-safe deduction), `GET /api/transactions/fraud-alerts`

### Excel Report Exports
- `GET /api/reports/inventory` (.xlsx)
- `GET /api/reports/distribution` (.xlsx)
- `GET /api/reports/predictions` (.xlsx)
- `GET /api/reports/fraud` (.xlsx)

---

## 8. College Viva Defense Guide

1. **Why use `threading.Lock`?**  
   In concurrent systems, multiple Fair Price Shops may deduct inventory at the exact same millisecond. Without synchronization locks, race conditions cause dirty reads and negative stock. `threading.Lock` makes read-check-deduct operations atomic.
2. **Why Isolation Forest for anomaly detection?**  
   Unlike distance-based outlier detectors that suffer in higher dimensions, Isolation Forest isolates anomalies by randomly partitioning feature space. Outliers require significantly fewer splits to isolate, making it linear in time complexity and highly effective for tabular transaction data.
3. **Why load models at startup rather than retraining per request?**  
   Retraining an ML model per request creates severe API latency and excessive CPU utilization. Serializing the trained artifact with Joblib allows sub-10ms inference.
4. **How was data leakage avoided?**  
   Feature engineering and scaling were performed with a strict Scikit-Learn `ColumnTransformer` fitted solely on the training partition. Lags ($t-1$) and rolling averages were derived chronologically without looking ahead into future intervals.
