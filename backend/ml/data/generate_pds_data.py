import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Fix seed for reproducibility
np.random.seed(42)

OUTPUT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_demand_dataset():
    """
    Generates a realistic, high-fidelity PDS historical demand dataset based on
    Indian National Food Security Act (NFSA) allocation standards and Targeted Public Distribution System (TPDS).
    
    Covers:
    - 5 Regions: Chennai, Coimbatore, Madurai, Salem, Tiruchirappalli
    - 4 Commodities: Rice, Wheat, Sugar, Dal
    - 36 Months: Jan 2022 to Dec 2024
    - Realistic seasonality: Pongal festival (Jan), Diwali festival (Oct/Nov), Summer buffer demand
    - Lag features: previous_month_demand, previous_month_offtake, 3m_rolling_avg
    """
    regions = ["Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli"]
    commodities = ["Rice", "Wheat", "Sugar", "Dal"]
    
    # Regional baseline beneficiary card counts
    region_base_cards = {
        "Chennai": 12500,
        "Coimbatore": 9800,
        "Madurai": 8200,
        "Salem": 6900,
        "Tiruchirappalli": 7400
    }
    
    # Base per-beneficiary monthly quota in kg
    commodity_base_quota = {
        "Rice": 5.0,     # Primary staple
        "Wheat": 2.5,    # Secondary cereal
        "Sugar": 1.0,    # Essential sweetener
        "Dal": 0.8       # Pulses
    }
    
    records = []
    
    dates = pd.date_range(start="2022-01-01", end="2024-12-01", freq="MS")
    
    for region in regions:
        base_cards = region_base_cards[region]
        
        for commodity in commodities:
            base_quota = commodity_base_quota[commodity]
            
            # Maintain running historical demand for lag computation
            prev_demand = None
            prev_offtake = None
            history_buffer = []
            
            for dt in dates:
                month = dt.month
                year = dt.year
                
                # Gradual annual population/beneficiary card growth (~2.5% per year)
                growth_factor = 1.0 + (year - 2022) * 0.025 + np.random.normal(0, 0.005)
                beneficiary_count = int(base_cards * growth_factor)
                avg_family_size = round(np.random.normal(3.8, 0.15), 1)
                
                # Seasonality & Festivals:
                # Jan: Pongal festival (huge Rice & Sugar demand spike)
                # Oct-Nov: Diwali festive distribution
                # July-Aug: Monsoon harvest transitions
                seasonal_multiplier = 1.0
                is_festive_month = 0
                if month == 1:
                    is_festive_month = 1
                    seasonal_multiplier = 1.25 if commodity in ["Rice", "Sugar"] else 1.08
                elif month in [10, 11]:
                    is_festive_month = 1
                    seasonal_multiplier = 1.18 if commodity in ["Sugar", "Dal", "Wheat"] else 1.10
                elif month in [5, 6]:
                    # Summer peak
                    seasonal_multiplier = 1.04
                else:
                    seasonal_multiplier = 0.98 + np.sin(month / 12 * 2 * np.pi) * 0.03

                # Theoretical base demand
                raw_demand = beneficiary_count * base_quota * seasonal_multiplier
                # Add natural variance
                noise = np.random.normal(0, 0.02) * raw_demand
                monthly_demand = round(raw_demand + noise, 1)

                # Initialize lags for the first iteration
                if prev_demand is None:
                    prev_demand = round(monthly_demand * 0.98, 1)
                    prev_offtake = round(monthly_demand * 0.96, 1)
                    history_buffer = [prev_demand, prev_demand, prev_demand]
                
                # 3-month historical rolling average
                hist_avg = round(np.mean(history_buffer[-3:]), 1)
                
                # Stock and allocation calculations
                allocated_quota = round(monthly_demand * np.random.uniform(1.02, 1.08), 1)
                # Current stock in warehouse before fresh procurement
                current_stock = round(monthly_demand * np.random.uniform(0.70, 1.15), 1)
                
                # Offtake is actual distribution (typically 94% - 99% of demand)
                actual_offtake = round(monthly_demand * np.random.uniform(0.94, 0.99), 1)
                
                # Target variable: required_quantity / monthly_demand (in kg)
                records.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "year": year,
                    "month": month,
                    "region": region,
                    "commodity": commodity,
                    "beneficiary_count": beneficiary_count,
                    "avg_family_size": avg_family_size,
                    "previous_month_demand": prev_demand,
                    "previous_month_offtake": prev_offtake,
                    "historical_average_3m": hist_avg,
                    "current_stock": current_stock,
                    "allocated_quota": allocated_quota,
                    "is_festive_month": is_festive_month,
                    "seasonal_index": round(seasonal_multiplier, 3),
                    "monthly_demand": monthly_demand
                })
                
                # Update lag buffers
                prev_demand = monthly_demand
                prev_offtake = actual_offtake
                history_buffer.append(monthly_demand)

    df_demand = pd.DataFrame(records)
    demand_csv = OUTPUT_DIR / "pds_demand_data.csv"
    df_demand.to_csv(demand_csv, index=False)
    print(f"Generated demand dataset with {len(df_demand)} records: {demand_csv}")
    return df_demand


def generate_transaction_dataset():
    """
    Generates individual PDS ration shop distribution transaction records.
    Contains normal cardholder distributions and realistic anomalous behaviors:
    - Normal card distribution within family entitlement quota
    - Anomalies: Ghost cards (excessive quantity), rapid repeat collections, off-hours claims
    """
    regions = ["Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli"]
    commodities = ["Rice", "Wheat", "Sugar", "Dal"]
    card_types = [
        ("Antyodaya Anna Yojana (AAY)", 0.20),
        ("Priority (PHH)", 0.65),
        ("Non-Priority (NPHH)", 0.15)
    ]
    
    # 2500 historical transaction logs
    num_txns = 2500
    txn_records = []
    
    start_date = datetime(2024, 1, 1)
    
    for i in range(1, num_txns + 1):
        txn_id = f"TXN-{10000 + i}"
        region = np.random.choice(regions)
        commodity = np.random.choice(commodities, p=[0.45, 0.25, 0.15, 0.15])
        beneficiary_id = f"BEN{np.random.randint(1, 400):03d}"
        ration_shop_id = f"FPS-{region[:3].upper()}-{np.random.randint(1, 3):03d}"
        
        # Select card type
        card_choice = np.random.choice([c[0] for c in card_types], p=[c[1] for c in card_types])
        family_size = np.random.randint(2, 6)
        
        # Calculate standard monthly quota entitlement
        if "AAY" in card_choice:
            entitled_quota = 25.0 if commodity == "Rice" else (10.0 if commodity == "Wheat" else 2.0)
        elif "Priority" in card_choice:
            entitled_quota = (family_size * 5.0) if commodity == "Rice" else ((family_size * 2.0) if commodity == "Wheat" else 1.0)
        else:
            entitled_quota = (family_size * 3.0) if commodity == "Rice" else ((family_size * 1.5) if commodity == "Wheat" else 1.0)
            
        # Timestamp
        day_offset = np.random.randint(0, 300)
        hour = np.random.choice(range(8, 20)) # standard PDS shop hours: 8am - 8pm
        txn_time = start_date + timedelta(days=day_offset, hours=int(hour), minutes=int(np.random.randint(0, 60)))
        
        # Time since last transaction (days)
        time_since_last_txn = float(np.random.exponential(scale=25.0) + 1.0)
        monthly_frequency = int(np.random.poisson(lam=1.2) + 1)
        
        # 4% probability of anomalous transaction
        is_anomaly = (np.random.random() < 0.04)
        
        if not is_anomaly:
            # Normal distribution: full quota or partial quota
            quantity = round(entitled_quota * np.random.uniform(0.70, 1.0), 1)
            is_anomaly_label = 0
            risk_label = "NORMAL"
        else:
            anomaly_type = np.random.choice(["BULK_EXCESS", "FREQUENT_REPEAT", "OFF_HOURS"])
            if anomaly_type == "BULK_EXCESS":
                quantity = round(entitled_quota * np.random.uniform(2.5, 5.0), 1)
            elif anomaly_type == "FREQUENT_REPEAT":
                quantity = round(entitled_quota * np.random.uniform(0.9, 1.2), 1)
                time_since_last_txn = round(np.random.uniform(0.2, 1.5), 1)  # only 1 day since prior draw
                monthly_frequency = np.random.randint(4, 8)
            else:
                quantity = round(entitled_quota * 1.5, 1)
                txn_time = txn_time.replace(hour=np.random.choice([1, 2, 23])) # midnight draw
            
            is_anomaly_label = 1
            risk_label = "SUSPICIOUS"

        txn_records.append({
            "transaction_id": txn_id,
            "beneficiary_id": beneficiary_id,
            "ration_shop_id": ration_shop_id,
            "region": region,
            "commodity": commodity,
            "card_type": card_choice,
            "family_size": family_size,
            "entitled_quota": entitled_quota,
            "quantity": quantity,
            "quantity_to_quota_ratio": round(quantity / (entitled_quota + 1e-5), 3),
            "days_since_prior_txn": round(time_since_last_txn, 1),
            "monthly_frequency": monthly_frequency,
            "timestamp": txn_time.strftime("%Y-%m-%d %H:%M:%S"),
            "hour": txn_time.hour,
            "is_anomaly": is_anomaly_label,
            "risk_label": risk_label
        })

    df_txn = pd.DataFrame(txn_records)
    txn_csv = OUTPUT_DIR / "pds_transactions.csv"
    df_txn.to_csv(txn_csv, index=False)
    print(f"Generated transactions dataset with {len(df_txn)} records: {txn_csv}")
    return df_txn


if __name__ == "__main__":
    generate_demand_dataset()
    generate_transaction_dataset()
