import io
import openpyxl
import pytest
from backend.app import create_app
from backend.services.inventory_service import InventoryService
from backend.services.report_service import ReportService
from backend.database.mongo import get_db


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_inventory_alerts_calculations_against_db(client):
    """
    Item 1: Verify total stock, shortage count, and procurement calculations against database records.
    """
    res = client.get("/api/inventory/alerts")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    alerts = data["data"]
    assert len(alerts) > 0

    # Calculate directly from alert items
    calc_total_stock = round(sum(a["current_stock"] for a in alerts), 2)
    calc_total_shortage = round(sum(a["shortage"] for a in alerts), 2)
    calc_total_procurement = round(sum(a["recommended_procurement"] for a in alerts), 2)
    calc_shortage_count = sum(1 for a in alerts if a["shortage"] > 0 or a["status"] == "SHORTAGE")
    calc_sufficient_count = sum(1 for a in alerts if a["status"] == "SUFFICIENT")
    calc_surplus_count = sum(1 for a in alerts if a["status"] in ("SURPLUS", "EXCESS"))

    # Assert server aggregates exactly match individual records
    assert data["total_stock"] == calc_total_stock
    assert data["total_shortage"] == calc_total_shortage
    assert data["total_procurement"] == calc_total_procurement
    assert data["shortage_count"] == calc_shortage_count
    assert data["sufficient_count"] == calc_sufficient_count
    assert data["surplus_count"] == calc_surplus_count
    assert calc_shortage_count + calc_sufficient_count + calc_surplus_count == len(alerts)

    # Verify against MongoDB collection directly
    db = get_db()
    db_items = list(db.inventory.find({}, {"_id": 0}))
    db_total_stock = round(sum(float(i.get("current_stock", 0)) for i in db_items), 2)
    assert calc_total_stock == db_total_stock


def test_prevent_negative_inventory_on_update(client):
    """
    Item 2: Validate stock updates and prevent negative inventory.
    """
    # 1. Negative stock via PUT /api/inventory/update-stock must be rejected with 400
    res_neg = client.put("/api/inventory/update-stock", json={
        "commodity": "Rice",
        "region": "Chennai",
        "current_stock": -150.0
    })
    assert res_neg.status_code == 400
    data_neg = res_neg.get_json()
    assert "cannot be negative" in data_neg["message"]

    # 2. Non-numeric stock must be rejected with 400
    res_nan = client.put("/api/inventory/update-stock", json={
        "commodity": "Rice",
        "region": "Chennai",
        "current_stock": "not-a-number"
    })
    assert res_nan.status_code == 400

    # 3. Direct InventoryService.update_stock must raise ValueError on negative stock
    with pytest.raises(ValueError) as excinfo:
        InventoryService.update_stock("Rice", "Chennai", -25.0)
    assert "cannot be negative" in str(excinfo.value)


def test_stock_edit_refreshes_alerts_and_procurement(client):
    """
    Item 3: After editing stock, automatically refresh summary cards, shortage status, and procurement.
    """
    region = "InventoryEditTestRegion"
    commodity = "Rice"

    try:
        # Create test inventory record with 100 kg stock
        InventoryService.update_stock(commodity, region, 100.0)

        # Get initial alert
        alerts_before = InventoryService.calculate_inventory_alerts(region=region, commodity=commodity)
        assert len(alerts_before) == 1
        item_before = alerts_before[0]
        demand = item_before["predicted_demand"]
        assert item_before["current_stock"] == 100.0
        assert item_before["shortage"] == round(max(0.0, demand - 100.0), 2)

        # Update stock via API to well above demand (e.g. 10,000 kg)
        res_update = client.put("/api/inventory/update-stock", json={
            "commodity": commodity,
            "region": region,
            "current_stock": 10000.0
        })
        assert res_update.status_code == 200

        # Verify alerts immediately reflect updated stock, zero shortage, and excess or sufficient status
        alerts_after = InventoryService.calculate_inventory_alerts(region=region, commodity=commodity)
        assert len(alerts_after) == 1
        item_after = alerts_after[0]
        assert item_after["current_stock"] == 10000.0
        assert item_after["shortage"] == 0.0
        assert item_after["recommended_procurement"] == 0.0
        assert item_after["status"] in ["SUFFICIENT", "EXCESS", "SURPLUS"]
    finally:
        db = get_db()
        db.inventory.delete_many({"region": region})


def test_safety_stock_procurement_consistency():
    """
    Item 4: Ensure procurement calculations consistently use predicted demand and current stock,
    including safety stock only where configured.
    """
    # 1. include_safety_stock=False (Default standard PDS procurement = demand shortage)
    alerts_no_safety = InventoryService.calculate_inventory_alerts(include_safety_stock=False)
    for a in alerts_no_safety:
        assert a["safety_stock_included"] is False
        if a["status"] == "SHORTAGE":
            assert a["recommended_procurement"] == a["shortage"]
        else:
            assert a["recommended_procurement"] == 0.0

    # 2. include_safety_stock=True (Procurement includes buffer restoration)
    alerts_with_safety = InventoryService.calculate_inventory_alerts(include_safety_stock=True)
    for a in alerts_with_safety:
        assert a["safety_stock_included"] is True
        expected_proc = round(max(0.0, (a["predicted_demand"] + a["buffer_stock"]) - a["current_stock"]), 2)
        assert a["recommended_procurement"] == expected_proc


def test_district_and_commodity_filters_working_together(client):
    """
    Item 5: Verify district and commodity filters work correctly together.
    """
    # 1. Both filters: Chennai + Rice
    res_both = client.get("/api/inventory/alerts?region=Chennai&commodity=Rice")
    assert res_both.status_code == 200
    data_both = res_both.get_json()["data"]
    assert len(data_both) == 1
    assert data_both[0]["region"] == "Chennai"
    assert data_both[0]["commodity"] == "Rice"

    # 2. Region only: Coimbatore
    res_reg = client.get("/api/inventory/alerts?region=Coimbatore")
    assert res_reg.status_code == 200
    data_reg = res_reg.get_json()["data"]
    assert len(data_reg) == 4
    assert all(d["region"] == "Coimbatore" for d in data_reg)

    # 3. Commodity only: Wheat
    res_com = client.get("/api/inventory/alerts?commodity=Wheat")
    assert res_com.status_code == 200
    data_com = res_com.get_json()["data"]
    assert len(data_com) == 5
    assert all(d["commodity"] == "Wheat" for d in data_com)


def test_inventory_changes_consistent_with_excel_reports(client):
    """
    Item 6: Ensure inventory changes remain consistent with distribution transactions and Excel reports.
    """
    res = client.get("/api/reports/inventory?region=Chennai&commodity=Rice")
    assert res.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res.content_type

    wb = openpyxl.load_workbook(io.BytesIO(res.data))
    assert "Warehouse Inventory" in wb.sheetnames
    ws = wb["Warehouse Inventory"]

    rows = list(ws.iter_rows(values_only=True))
    assert len(rows) >= 2  # Header + 1 record
    headers = rows[0]
    assert headers[0] == "Commodity Name"
    assert headers[1] == "Depot District"
    assert headers[2] == "Current Warehouse Stock (kg)"

    data_row = rows[1]
    assert data_row[0] == "Rice"
    assert data_row[1] == "Chennai"
    # Last Stock Verification must not be 'N/A' when last_updated exists
    last_verification = data_row[6]
    assert last_verification != "N/A"


def test_inventory_difference_and_surplus_classification(client):
    """
    Item 7: Verify Difference calculation, Shortage/Sufficient/Surplus status classifications,
    and handling of sparse sample warnings without fabricating zero demand.
    """
    res = client.get("/api/inventory/alerts")
    assert res.status_code == 200
    data = res.get_json()
    alerts = data["data"]

    for alert in alerts:
        stock = alert["current_stock"]
        demand = alert["predicted_demand"]
        difference = alert.get("difference")
        status = alert["status"]

        # 1. Difference calculation: Difference == Current Stock - Predicted Demand
        expected_diff = round(stock - demand, 2)
        assert difference == expected_diff

        # 2. Status classification verification:
        if stock < demand:
            assert status == "SHORTAGE"
            assert alert["classification"] == "Shortage"
            assert alert["shortage"] == round(demand - stock, 2)
            assert alert["recommended_procurement"] == alert["shortage"]
        elif stock > round(demand * 1.5, 2):
            assert status in ["SURPLUS", "EXCESS"]
            assert alert["classification"] == "Surplus"
            assert alert["shortage"] == 0.0
            assert alert["recommended_procurement"] == 0.0
        else:
            assert status == "SUFFICIENT"
            assert alert["classification"] == "Sufficient"
            assert alert["shortage"] == 0.0
            assert alert["recommended_procurement"] == 0.0

        # 3. Forecast period metadata check and monthly demand period clarification
        assert "forecast_period" in alert
        assert "forecast_label" in alert
        assert alert.get("demand_period") == "MONTHLY"
        assert alert.get("demand_unit") == "kg/month"

        # 4. Check handling of sparse/zero predictions without fabricating genuine zero demand
        if alert.get("predicted_demand") == 0.0:
            assert alert["insufficient_data"] is True
            assert "Genuine monthly demand is not zero" in alert["data_quality_warning"]

    # Verify top-level API metadata reflects monthly timeframe
    assert data.get("demand_period") == "MONTHLY"
    assert data.get("demand_unit") == "kg/month"


def test_inventory_audit_history_persistence_and_api(client):
    """
    Item 8: Verify stock adjustment logs to inventory_audit, appends adjustment_history,
    and returns via GET /api/inventory/history.
    """
    test_region = "AuditTestRegion"
    test_commodity = "Wheat"
    test_user = "OfficerAuditTest"

    try:
        # Initial stock creation
        res1 = client.put("/api/inventory/update-stock", json={
            "commodity": test_commodity,
            "region": test_region,
            "current_stock": 500.0,
            "updated_by": test_user
        })
        assert res1.status_code == 200

        # Secondary stock adjustment
        res2 = client.put("/api/inventory/update-stock", json={
            "commodity": test_commodity,
            "region": test_region,
            "current_stock": 750.0,
            "updated_by": test_user
        })
        assert res2.status_code == 200
        data2 = res2.get_json()["data"]
        assert data2["previous_stock"] == 500.0
        assert data2["current_stock"] == 750.0
        assert data2["difference"] == 250.0
        assert data2["updated_by"] == test_user

        # Fetch audit history via endpoint
        res_hist = client.get(f"/api/inventory/history?region={test_region}")
        assert res_hist.status_code == 200
        hist_data = res_hist.get_json()["data"]
        assert len(hist_data) >= 2
        latest = hist_data[0]
        assert latest["region"] == test_region
        assert latest["commodity"] == test_commodity
        assert latest["new_stock"] == 750.0
        assert latest["previous_stock"] == 500.0
        assert latest["updated_by"] == test_user
    finally:
        db = get_db()
        db.inventory.delete_many({"region": test_region})
        db.inventory_audit.delete_many({"region": test_region})

