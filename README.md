# AI-Powered Smart Public Distribution System (SmartPDS)

An AI-based web application designed to improve Public Distribution System (PDS) operations through demand forecasting, anomaly detection, inventory management, and transparent ration distribution.

## 1. Key Features

- **Demand Forecasting:** Predicts monthly food-grain requirements using machine learning.
- **Anomaly Detection:** Uses Isolation Forest to flag unusual distribution transactions for officer review.
- **Inventory Management:** Tracks depot stock, shortages, surplus, and procurement requirements.
- **Beneficiary Management:** Maintains ration-card details and calculates PHH and AAY entitlements.
- **Transaction Management:** Records ration distribution and prevents duplicate submissions.
- **Dashboard & Reports:** Displays operational information and exports Excel reports.
- **Role-Based Access:** Provides separate access for administrators, district officers, and ration dealers.

## 2. Technology Stack

| Component | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript, Chart.js |
| Backend | Python, Flask |
| Database | MongoDB |
| Machine Learning | Scikit-learn, XGBoost |
| Data Processing | Pandas, NumPy |
| Testing | Pytest |
| Deployment | Docker, Docker Compose |

## 3. Machine Learning

**Demand Forecasting**
- Models: Linear Regression, Decision Tree, Random Forest, XGBoost.
- Uses historical demand, beneficiary count, commodity, region, and seasonal information.
- Compares models using MAE, MSE, RMSE, and R².

**Anomaly Detection**
- Algorithm: Isolation Forest.
- Identifies unusual transaction patterns.
- Flags suspicious transactions for manual verification; it does not automatically confirm fraud.

**Dataset:** Models are trained and evaluated using synthetically generated PDS datasets. Results are experimental and require validation using real distribution data.

## 4. System Architecture

```text
Frontend (HTML, CSS, JavaScript)
              |
         Flask REST API
              |
    Business Logic & ML Models
              |
           MongoDB
```

Docker Compose runs the application and database containers.

## 5. User Roles

- **Administrator:** Manages users, commodities, inventory, and system operations.
- **District Officer:** Monitors regional demand, inventory, and anomaly alerts.
- **FPS Dealer:** Records ration distribution and checks beneficiary details.

## 6. Installation

### Run using Docker

```bash
git clone https://github.com/fawaz165/AI-Powered-Smart-PDS.git
cd AI-Powered-Smart-PDS
cp .env.example .env
docker compose up -d --build
```

Open the application:

- Application: http://localhost:5000
- Health Check: http://localhost:5000/api/health
- ML Status: http://localhost:5000/api/ml-status

## 7. Testing

Run the automated test suite:

```bash
python -m pytest tests/ -v
```

The documented test run reports **81 passed tests**.

## 8. Limitations

- Uses synthetic datasets rather than real government distribution records.
- ML predictions require validation with real-world data.
- Anomaly detection identifies unusual patterns, not confirmed fraud.
- Government-system integration is not currently implemented.

## 9. Future Enhancements

- Biometric verification integration.
- IoT-based smart weighing scales.
- GPS-based transportation tracking.
- Integration with government PDS databases.
- Offline transaction support.

## 10. License

MIT License.
