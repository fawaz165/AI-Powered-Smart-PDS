import os
from pathlib import Path
from datetime import datetime
import pandas as pd
from backend.database.mongo import get_db
from backend.config import Config
from backend.utils.logger import logger

REPORTS_DIR = Config.REPORTS_DIR
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


class ReportService:
    """Generates analytical Excel spreadsheets for administrative export."""

    @classmethod
    def generate_inventory_report(cls) -> Path:
        """Exports full regional inventory status with stock and buffer analysis."""
        db = get_db()
        items = list(db.inventory.find({}, {"_id": 0}))
        df = pd.DataFrame(items)
        if df.empty:
            df = pd.DataFrame(columns=["commodity", "region", "current_stock", "buffer_stock", "unit"])

        filename = f"inventory_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = REPORTS_DIR / filename

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Current Inventory", index=False)

        logger.info(f"Generated inventory report: {filepath}")
        return filepath

    @classmethod
    def generate_distribution_report(cls) -> Path:
        """Exports grain distribution transaction log."""
        db = get_db()
        txns = list(db.transactions.find({}, {"_id": 0}))
        df = pd.DataFrame(txns)
        if df.empty:
            df = pd.DataFrame(columns=["transaction_id", "beneficiary_id", "commodity", "quantity", "region", "status"])

        filename = f"distribution_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = REPORTS_DIR / filename

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Transactions", index=False)

        logger.info(f"Generated distribution report: {filepath}")
        return filepath

    @classmethod
    def generate_fraud_report(cls) -> Path:
        """Exports flagged suspicious transactions and anomaly evaluations."""
        db = get_db()
        alerts = list(db.fraud_alerts.find({}, {"_id": 0}))
        df = pd.DataFrame(alerts)
        if df.empty:
            df = pd.DataFrame(columns=["transaction_id", "beneficiary_id", "commodity", "quantity", "risk_level", "reason"])

        filename = f"fraud_anomaly_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = REPORTS_DIR / filename

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Flagged Anomalies", index=False)

        logger.info(f"Generated fraud report: {filepath}")
        return filepath

    @classmethod
    def generate_predictions_report(cls) -> Path:
        """Exports ML demand predictions and procurement recommendations."""
        db = get_db()
        preds = list(db.predictions.find({}, {"_id": 0}))
        df = pd.DataFrame(preds)
        if df.empty:
            df = pd.DataFrame(columns=["commodity", "region", "predicted_demand", "current_stock", "shortage", "recommended_procurement"])

        filename = f"demand_predictions_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = REPORTS_DIR / filename

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Demand Predictions", index=False)

        logger.info(f"Generated demand predictions report: {filepath}")
        return filepath
