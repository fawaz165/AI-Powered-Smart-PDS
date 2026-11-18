import os
import pytest

# Ensure testing configuration BEFORE any application or database module is imported
os.environ["FLASK_ENV"] = "testing"
os.environ["TESTING"] = "true"
os.environ["DB_NAME"] = os.getenv("TEST_DB_NAME", "smart_pds_test_db")

# Point MONGO_URI to the test database
base_mongo = os.getenv("TEST_MONGO_URI") or os.getenv("MONGO_URI") or "mongodb://localhost:27017/smart_pds_test_db"
if "/" in base_mongo.split("://")[-1]:
    prefix = base_mongo.rsplit("/", 1)[0]
    os.environ["MONGO_URI"] = f"{prefix}/smart_pds_test_db"
else:
    os.environ["MONGO_URI"] = f"{base_mongo}/smart_pds_test_db"

from backend.database.mongo import Database, get_db
from backend.database.seed_db import seed_database


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Session-scoped fixture:
    - Establishes connection strictly to smart_pds_test_db.
    - Validates safety check that the active database is NOT production.
    - Seeds baseline test commodities, beneficiaries, and users.
    """
    db_inst = Database(
        uri=os.environ["MONGO_URI"],
        db_name=os.environ["DB_NAME"],
        force_reconnect=True
    )
    db = db_inst.db

    # CRITICAL SAFETY CHECK: Never allow test suite to execute against production/demo database
    assert "test" in db.name.lower(), (
        f"CRITICAL SAFETY VIOLATION: Test suite attempted to run against non-test database '{db.name}'. "
        f"Automated tests must run against a database containing 'test' (e.g., smart_pds_test_db)."
    )

    # Seed baseline records into smart_pds_test_db once for the test session
    seed_database(target_db=db)
    yield db


@pytest.fixture(autouse=True)
def clean_test_data():
    """
    Autouse fixture that runs before and after each test to ensure test records
    (e.g., ConcurrentTestRegion, BEN-CONCUR-*, FPS-TEST-*, TEST-*) are completely
    isolated and never leak between test executions.
    """
    db = get_db()
    assert "test" in db.name.lower(), f"Safety check failed: Active database '{db.name}' is not a test database!"

    def cleanup():
        test_selector = {
            "$or": [
                {"region": "ConcurrentTestRegion"},
                {"ration_shop_id": "FPS-TEST-001"},
                {"ration_shop_id": {"$regex": "^FPS-TEST"}},
                {"beneficiary_id": {"$in": ["BEN-CONCUR-A", "BEN-CONCUR-B", "BEN-EXCESS"]}},
                {"beneficiary_id": {"$regex": "^TEST-"}}
            ]
        }
        db.transactions.delete_many(test_selector)
        db.inventory.delete_many({"region": "ConcurrentTestRegion"})
        db.beneficiaries.delete_many({"beneficiary_id": {"$regex": "^TEST-"}})
        db.fraud_alerts.delete_many(test_selector)
        db.users.delete_many({"username": {"$regex": "_test$"}})

    cleanup()
    yield
    cleanup()
