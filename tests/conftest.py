import pytest
from backend.database.mongo import get_db


@pytest.fixture(autouse=True)
def clean_test_data():
    """
    Autouse fixture that runs before and after each test to ensure test records
    (e.g., ConcurrentTestRegion, BEN-CONCUR-*, FPS-TEST-*, TEST-*) are completely
    isolated and never leak into production or demonstration data collections.
    """
    db = get_db()

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

    # Clean up any leftover test data before test
    cleanup()
    yield
    # Clean up all created test data after test
    cleanup()
