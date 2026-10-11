import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.database.mongo import Database
from backend.models.user import UserModel
from backend.models.beneficiary import BeneficiaryModel
from backend.models.commodity import CommodityModel
from backend.models.inventory import InventoryModel
from backend.models.transaction import TransactionModel
from backend.utils.logger import logger


def seed_database():
    """Seeds the database with essential administrative data, initial commodities, inventory, and beneficiaries."""
    db_inst = Database()
    db = db_inst.db
    logger.info("Initializing database seed process...")

    # 1. Seed Administrative User
    if db.users.count_documents({"username": "admin"}) == 0:
        admin_doc = UserModel.create_user_doc(
            username="admin",
            password="admin123",
            role="admin",
            email="admin@smartpds.gov.in",
            full_name="PDS Chief Administrator"
        )
        db.users.insert_one(admin_doc)
        logger.info("Seeded primary admin user: admin / admin123")
    else:
        logger.info("Admin user already exists.")

    # 2. Seed Commodities with Configured Subsidized Prices & Official vs Demo Rates
    commodities = [
        {"commodity_code": "COM-RIC", "name": "Rice", "unit": "kg", "subsidized_price": 0.0, "market_price": 42.0, "rate_type": "OFFICIAL_NFSA", "description": "Fortified raw & boiled rice under NFSA entitlement"},
        {"commodity_code": "COM-WHT", "name": "Wheat", "unit": "kg", "subsidized_price": 2.0, "market_price": 34.0, "rate_type": "OFFICIAL_NFSA", "description": "Whole grain milled wheat flour"},
        {"commodity_code": "COM-SUG", "name": "Sugar", "unit": "kg", "subsidized_price": 13.5, "market_price": 45.0, "rate_type": "OFFICIAL_NFSA", "description": "Refined crystal sugar under AAY distribution"},
        {"commodity_code": "COM-DAL", "name": "Dal", "unit": "kg", "subsidized_price": 30.0, "market_price": 130.0, "rate_type": "DEMONSTRATION", "description": "Toor / Chana pulses under state welfare distribution"}
    ]
    for c in commodities:
        db.commodities.update_one(
            {"name": c["name"]},
            {"$set": CommodityModel.create_doc(
                commodity_code=c["commodity_code"],
                name=c["name"],
                unit=c["unit"],
                subsidized_price=c["subsidized_price"],
                description=c["description"],
                rate_type=c["rate_type"],
                market_price=c["market_price"]
            )},
            upsert=True
        )
    logger.info("Seeded 4 core commodities with verified official and demonstration rates")

    # 3. Seed Ration Shops
    ration_shops = [
        {"shop_id": "FPS-CHN-001", "name": "Anna Nagar Fair Price Shop 1", "region": "Chennai", "officer_in_charge": "S. Murugan"},
        {"shop_id": "FPS-CHN-002", "name": "T. Nagar Fair Price Shop 2", "region": "Chennai", "officer_in_charge": "K. Selvi"},
        {"shop_id": "FPS-CBE-001", "name": "RS Puram Fair Price Shop", "region": "Coimbatore", "officer_in_charge": "R. Prakash"},
        {"shop_id": "FPS-MDU-001", "name": "Simmakkal PDS Distribution Depot", "region": "Madurai", "officer_in_charge": "M. Alagappan"},
        {"shop_id": "FPS-SLM-001", "name": "Hasthampatti Fair Price Shop", "region": "Salem", "officer_in_charge": "T. Gunasekaran"},
        {"shop_id": "FPS-TRY-001", "name": "Thillai Nagar Fair Price Depot", "region": "Tiruchirappalli", "officer_in_charge": "V. Radhika"}
    ]
    for s in ration_shops:
        db.ration_shops.update_one(
            {"shop_id": s["shop_id"]},
            {"$set": s},
            upsert=True
        )
    logger.info("Seeded 6 Fair Price Shops across 5 districts")

    # 4. Seed Inventory with realistic stocks (including the prompt's exact 3,800 kg Rice Chennai scenario)
    inventory_items = [
        {"commodity": "Rice", "region": "Chennai", "current_stock": 3800.0, "buffer_stock": 500.0},
        {"commodity": "Wheat", "region": "Chennai", "current_stock": 2500.0, "buffer_stock": 400.0},
        {"commodity": "Sugar", "region": "Chennai", "current_stock": 1100.0, "buffer_stock": 200.0},
        {"commodity": "Dal", "region": "Chennai", "current_stock": 850.0, "buffer_stock": 150.0},
        
        {"commodity": "Rice", "region": "Coimbatore", "current_stock": 4200.0, "buffer_stock": 500.0},
        {"commodity": "Wheat", "region": "Coimbatore", "current_stock": 1900.0, "buffer_stock": 400.0},
        {"commodity": "Sugar", "region": "Coimbatore", "current_stock": 950.0, "buffer_stock": 200.0},
        {"commodity": "Dal", "region": "Coimbatore", "current_stock": 700.0, "buffer_stock": 150.0},

        {"commodity": "Rice", "region": "Madurai", "current_stock": 3100.0, "buffer_stock": 500.0},
        {"commodity": "Wheat", "region": "Madurai", "current_stock": 1600.0, "buffer_stock": 350.0},
        {"commodity": "Sugar", "region": "Madurai", "current_stock": 800.0, "buffer_stock": 200.0},
        {"commodity": "Dal", "region": "Madurai", "current_stock": 620.0, "buffer_stock": 150.0},

        {"commodity": "Rice", "region": "Salem", "current_stock": 2900.0, "buffer_stock": 450.0},
        {"commodity": "Wheat", "region": "Salem", "current_stock": 1400.0, "buffer_stock": 300.0},
        {"commodity": "Sugar", "region": "Salem", "current_stock": 750.0, "buffer_stock": 180.0},
        {"commodity": "Dal", "region": "Salem", "current_stock": 540.0, "buffer_stock": 120.0},

        {"commodity": "Rice", "region": "Tiruchirappalli", "current_stock": 3300.0, "buffer_stock": 450.0},
        {"commodity": "Wheat", "region": "Tiruchirappalli", "current_stock": 1550.0, "buffer_stock": 300.0},
        {"commodity": "Sugar", "region": "Tiruchirappalli", "current_stock": 820.0, "buffer_stock": 180.0},
        {"commodity": "Dal", "region": "Tiruchirappalli", "current_stock": 580.0, "buffer_stock": 120.0},
    ]
    for inv in inventory_items:
        db.inventory.update_one(
            {"commodity": inv["commodity"], "region": inv["region"]},
            {"$set": InventoryModel.create_doc(
                commodity=inv["commodity"],
                region=inv["region"],
                current_stock=inv["current_stock"],
                buffer_stock=inv["buffer_stock"]
            )},
            upsert=True
        )
    logger.info("Seeded 20 regional inventory commodity stocks")

    # 5. Seed Beneficiaries
    sample_beneficiaries = [
        {"beneficiary_id": "BEN001", "name": "Aarav Sharma", "region": "Chennai", "family_size": 4, "ration_card_type": "Priority (PHH)"},
        {"beneficiary_id": "BEN002", "name": "Meenakshi Sundaram", "region": "Chennai", "family_size": 3, "ration_card_type": "Antyodaya Anna Yojana (AAY)"},
        {"beneficiary_id": "BEN003", "name": "Kavitha Rajan", "region": "Chennai", "family_size": 5, "ration_card_type": "Priority (PHH)"},
        {"beneficiary_id": "BEN004", "name": "Dinesh Kumar", "region": "Chennai", "family_size": 2, "ration_card_type": "Non-Priority (NPHH)"},
        {"beneficiary_id": "BEN005", "name": "Ananya Krishnan", "region": "Coimbatore", "family_size": 4, "ration_card_type": "Priority (PHH)"},
        {"beneficiary_id": "BEN006", "name": "Subramanian Velu", "region": "Coimbatore", "family_size": 6, "ration_card_type": "Antyodaya Anna Yojana (AAY)"},
        {"beneficiary_id": "BEN007", "name": "Lakshmi Narayanan", "region": "Madurai", "family_size": 4, "ration_card_type": "Priority (PHH)"},
        {"beneficiary_id": "BEN008", "name": "Gopalakrishnan P", "region": "Salem", "family_size": 3, "ration_card_type": "Priority (PHH)"},
        {"beneficiary_id": "BEN009", "name": "Farhan Ahmed", "region": "Tiruchirappalli", "family_size": 5, "ration_card_type": "Antyodaya Anna Yojana (AAY)"},
        {"beneficiary_id": "BEN010", "name": "Stella Mary", "region": "Chennai", "family_size": 4, "ration_card_type": "Priority (PHH)"}
    ]
    for b in sample_beneficiaries:
        db.beneficiaries.update_one(
            {"beneficiary_id": b["beneficiary_id"]},
            {"$set": BeneficiaryModel.create_doc(
                beneficiary_id=b["beneficiary_id"],
                name=b["name"],
                region=b["region"],
                family_size=b["family_size"],
                ration_card_type=b["ration_card_type"]
            )},
            upsert=True
        )
    logger.info(f"Seeded {len(sample_beneficiaries)} sample cardholder beneficiaries")

    # 6. Seed Realistic Demonstration Transactions (All 5 Districts, Multi-Commodity)
    # Safely purge any test artifacts if present
    db.transactions.delete_many({
        "$or": [
            {"region": "ConcurrentTestRegion"},
            {"ration_shop_id": "FPS-TEST-001"},
            {"ration_shop_id": {"$regex": "^FPS-TEST"}},
            {"beneficiary_id": {"$in": ["BEN-CONCUR-A", "BEN-CONCUR-B", "BEN-EXCESS"]}},
            {"beneficiary_id": {"$regex": "^TEST-"}}
        ]
    })
    db.inventory.delete_many({"region": "ConcurrentTestRegion"})

    now = datetime.utcnow()
    txns = [
        TransactionModel.create_doc("TXN-1001", "BEN001", "FPS-CHN-001", "Rice", 20.0, "Chennai", now - timedelta(days=2),
                                   reason="Regular monthly quota distribution"),
        TransactionModel.create_doc("TXN-1002", "BEN001", "FPS-CHN-001", "Wheat", 8.0, "Chennai", now - timedelta(days=2),
                                   reason="Priority household subsidized wheat allotment"),
        TransactionModel.create_doc("TXN-1003", "BEN002", "FPS-CHN-001", "Rice", 25.0, "Chennai", now - timedelta(days=1),
                                   reason="Antyodaya Anna Yojana monthly grain quota"),
        TransactionModel.create_doc("TXN-1004", "BEN003", "FPS-CHN-002", "Rice", 25.0, "Chennai", now - timedelta(hours=18),
                                   reason="Priority household monthly grain distribution"),
        TransactionModel.create_doc("TXN-1005", "BEN005", "FPS-CBE-001", "Rice", 20.0, "Coimbatore", now - timedelta(hours=14),
                                   reason="Priority household monthly distribution"),
        # Sample Flagged Anomaly for Demonstration
        TransactionModel.create_doc("TXN-1006", "BEN004", "FPS-CHN-001", "Rice", 95.0, "Chennai", now - timedelta(hours=8),
                                   status="SUSPICIOUS", risk_level="HIGH", anomaly_score=-0.38,
                                   reason="Single withdrawal 95 kg exceeds allowed family entitlement of 6 kg by 15.8x"),
        TransactionModel.create_doc("TXN-1007", "BEN006", "FPS-CBE-001", "Wheat", 10.0, "Coimbatore", now - timedelta(hours=6),
                                   reason="AAY family monthly wheat distribution"),
        TransactionModel.create_doc("TXN-1008", "BEN006", "FPS-CBE-001", "Sugar", 2.0, "Coimbatore", now - timedelta(hours=5),
                                   reason="Subsidized household sugar entitlement"),
        TransactionModel.create_doc("TXN-1009", "BEN007", "FPS-MDU-001", "Rice", 20.0, "Madurai", now - timedelta(hours=4),
                                   reason="Priority household monthly grain distribution"),
        TransactionModel.create_doc("TXN-1010", "BEN007", "FPS-MDU-001", "Dal", 2.0, "Madurai", now - timedelta(hours=3),
                                   reason="State welfare subsidized pulse quota"),
        TransactionModel.create_doc("TXN-1011", "BEN008", "FPS-SLM-001", "Rice", 15.0, "Salem", now - timedelta(hours=2, minutes=30),
                                   reason="Priority household monthly grain distribution"),
        TransactionModel.create_doc("TXN-1012", "BEN008", "FPS-SLM-001", "Wheat", 5.0, "Salem", now - timedelta(hours=2),
                                   reason="Subsidized whole grain wheat quota"),
        TransactionModel.create_doc("TXN-1013", "BEN009", "FPS-TRY-001", "Rice", 25.0, "Tiruchirappalli", now - timedelta(hours=1, minutes=15),
                                   reason="Antyodaya Anna Yojana monthly grain quota"),
        TransactionModel.create_doc("TXN-1014", "BEN009", "FPS-TRY-001", "Sugar", 2.0, "Tiruchirappalli", now - timedelta(minutes=45),
                                   reason="Subsidized household crystal sugar quota"),
        TransactionModel.create_doc("TXN-1015", "BEN010", "FPS-CHN-002", "Rice", 20.0, "Chennai", now - timedelta(minutes=15),
                                   reason="Priority household monthly grain distribution")
    ]
    for txn in txns:
        db.transactions.update_one(
            {"transaction_id": txn["transaction_id"]},
            {"$set": txn},
            upsert=True
        )
    logger.info(f"Seeded {len(txns)} realistic demonstration transactions across all 5 districts")

    # Also register the anomalous transaction in fraud_alerts collection
    db.fraud_alerts.update_one(
        {"transaction_id": "TXN-1006"},
        {"$set": {
            "transaction_id": "TXN-1006",
            "beneficiary_id": "BEN004",
            "ration_shop_id": "FPS-CHN-001",
            "commodity": "Rice",
            "quantity": 95.0,
            "region": "Chennai",
            "risk_level": "HIGH",
            "anomaly_score": -0.38,
            "status": "PENDING_REVIEW",
            "reason": "Single withdrawal 95 kg exceeds allowed family entitlement of 6 kg by 15.8x",
            "created_at": now - timedelta(hours=8)
        }},
        upsert=True
    )

    logger.info("Database seeding completed successfully.")


if __name__ == "__main__":
    seed_database()
