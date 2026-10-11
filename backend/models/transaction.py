from datetime import datetime


class TransactionModel:
    """PDS Grain Distribution Transaction."""
    @staticmethod
    def create_doc(transaction_id, beneficiary_id, ration_shop_id, commodity, quantity,
                   region="Chennai", timestamp=None, status="NORMAL", risk_level="LOW",
                   anomaly_score=0.0, reason=None, commodity_code=None):
        comm_name = commodity.strip()
        code = (commodity_code or (
            "COM-RIC" if comm_name.lower() == "rice" else (
                "COM-WHT" if comm_name.lower() == "wheat" else (
                    "COM-SUG" if comm_name.lower() == "sugar" else (
                        "COM-DAL" if comm_name.lower() == "dal" else f"COM-{comm_name[:3].upper()}"
                    )
                )
            )
        )).strip().upper()

        return {
            "transaction_id": transaction_id.strip().upper(),
            "beneficiary_id": beneficiary_id.strip().upper(),
            "ration_shop_id": ration_shop_id.strip().upper(),
            "commodity": comm_name,
            "commodity_code": code,
            "quantity": float(quantity),
            "region": region.strip(),
            "timestamp": timestamp or datetime.utcnow(),
            "status": status,             # NORMAL, SUSPICIOUS, HIGH_RISK
            "risk_level": risk_level,     # LOW, MEDIUM, HIGH
            "anomaly_score": float(anomaly_score),
            "reason": reason or "Normal monthly quota distribution",
            "is_flagged": (status != "NORMAL")
        }
