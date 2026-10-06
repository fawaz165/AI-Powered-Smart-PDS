from datetime import datetime


class TransactionModel:
    """PDS Grain Distribution Transaction."""
    @staticmethod
    def create_doc(transaction_id, beneficiary_id, ration_shop_id, commodity, quantity,
                   region="Chennai", timestamp=None, status="NORMAL", risk_level="LOW",
                   anomaly_score=0.0, reason=None):
        return {
            "transaction_id": transaction_id.strip().upper(),
            "beneficiary_id": beneficiary_id.strip().upper(),
            "ration_shop_id": ration_shop_id.strip().upper(),
            "commodity": commodity.strip(),
            "quantity": float(quantity),
            "region": region.strip(),
            "timestamp": timestamp or datetime.utcnow(),
            "status": status,             # NORMAL, SUSPICIOUS, HIGH_RISK
            "risk_level": risk_level,     # LOW, MEDIUM, HIGH
            "anomaly_score": float(anomaly_score),
            "reason": reason or "Normal monthly quota distribution",
            "is_flagged": (status != "NORMAL")
        }
