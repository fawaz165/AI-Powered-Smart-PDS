import threading
import pytest
from backend.services.inventory_service import InventoryService


def test_thread_safe_inventory_example_scenario():
    """
    Directly tests the prompt's mandated example:
    Initial stock = 100 kg
    Transaction A = 30 kg
    Transaction B = 40 kg
    Final stock must correctly become: 30 kg
    """
    commodity = "Rice"
    region = "ConcurrentTestRegion"

    # Set initial stock to exactly 100 kg
    InventoryService.update_stock(commodity, region, 100.0)
    assert InventoryService.get_stock(commodity, region)["current_stock"] == 100.0

    # Execute Transaction A (30 kg) and Transaction B (40 kg) concurrently using Python threads
    results = []

    def run_txn(qty, ben_id):
        res = InventoryService.process_transaction_distribution(
            commodity=commodity,
            region=region,
            quantity=qty,
            beneficiary_id=ben_id,
            ration_shop_id="FPS-TEST-001"
        )
        results.append(res)

    t1 = threading.Thread(target=run_txn, args=(30.0, "BEN-CONCUR-A"))
    t2 = threading.Thread(target=run_txn, args=(40.0, "BEN-CONCUR-B"))

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # Verify both transactions succeeded
    assert len(results) == 2
    assert results[0]["success"] is True
    assert results[1]["success"] is True

    # Final stock must correctly become 30 kg! (100 - 30 - 40 = 30)
    final_stock_doc = InventoryService.get_stock(commodity, region)
    assert final_stock_doc["current_stock"] == 30.0


def test_thread_safe_negative_stock_rejection():
    """
    Verifies that when stock is 30 kg, an attempted concurrent transaction of 50 kg is
    safely rejected without causing negative warehouse inventory.
    """
    commodity = "Rice"
    region = "ConcurrentTestRegion"

    # Current stock is 30 kg from previous test
    # Attempting to withdraw 50 kg should be rejected
    rejected_res = InventoryService.process_transaction_distribution(
        commodity=commodity,
        region=region,
        quantity=50.0,
        beneficiary_id="BEN-EXCESS",
        ration_shop_id="FPS-TEST-001"
    )

    assert rejected_res["success"] is False
    assert "Insufficient stock" in rejected_res["message"]

    # Stock must remain safely unchanged at 30 kg
    stock_doc = InventoryService.get_stock(commodity, region)
    assert stock_doc["current_stock"] == 30.0
