import os
import re
from pathlib import Path
from datetime import datetime
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from backend.database.mongo import get_db
from backend.config import Config
from backend.utils.logger import logger

REPORTS_DIR = Config.REPORTS_DIR
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


class ReportService:
    """
    Generates structured, database-backed Excel spreadsheets with support
    for district, date, commodity, and risk filtering, styled using OpenPyXL.
    """

    @staticmethod
    def _apply_excel_formatting(filepath: Path, sheet_name: str, title: str):
        """Applies professional administrative styling: dark headers, auto-filters, freeze panes, number formats."""
        try:
            wb = openpyxl.load_workbook(filepath)
            ws = wb[sheet_name]

            # Enable auto-filter across all columns
            if ws.max_column and ws.max_row:
                ws.auto_filter.ref = ws.dimensions

            # Freeze the top header row so it stays pinned on scroll
            ws.freeze_panes = "A2"

            header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
            thin_border = Border(
                left=Side(style="thin", color="CBD5E1"),
                right=Side(style="thin", color="CBD5E1"),
                top=Side(style="thin", color="CBD5E1"),
                bottom=Side(style="thin", color="CBD5E1")
            )

            # Style header row (Row 1)
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            ws.row_dimensions[1].height = 28

            # Format data rows & adjust column widths
            for row_idx in range(2, ws.max_row + 1):
                is_even = (row_idx % 2 == 0)
                ws.row_dimensions[row_idx].height = 20
                for col_idx in range(1, ws.max_column + 1):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    cell.border = thin_border
                    if is_even:
                        cell.fill = zebra_fill
                    
                    val = cell.value
                    header_val = str(ws.cell(row=1, column=col_idx).value or "").lower()

                    # Format numbers appropriately
                    if isinstance(val, (int, float)):
                        if "score" in header_val:
                            cell.number_format = "0.0000"
                            cell.alignment = Alignment(horizontal="right", vertical="center")
                        elif any(k in header_val for k in ["month", "year", "cardholders"]):
                            cell.number_format = "#,##0"
                            cell.alignment = Alignment(horizontal="center", vertical="center")
                        elif any(k in header_val for k in ["(kg)", "quantity", "stock", "buffer", "shortage", "procurement", "demand", "difference", "capacity"]):
                            cell.number_format = "#,##0.0"
                            cell.alignment = Alignment(horizontal="right", vertical="center")
                        else:
                            cell.alignment = Alignment(horizontal="right", vertical="center")
                    elif isinstance(val, str):
                        if any(k in header_val for k in ["id", "code", "date", "time", "district", "region", "status", "level", "decision", "ratio", "multiplier", "interval", "model"]):
                            cell.alignment = Alignment(horizontal="center", vertical="center")
                        else:
                            cell.alignment = Alignment(horizontal="left", vertical="center")

            # Auto-fit column widths
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val_str = str(cell.value or "")
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                ws.column_dimensions[col_letter].width = max(min(max_len + 4, 45), 14)

            wb.save(filepath)
        except Exception as e:
            logger.warning(f"Failed to apply openpyxl formatting to {filepath}: {e}")

    @staticmethod
    def _parse_date_bound(date_str: str, is_end: bool = False):
        """Parses YYYY-MM-DD string into datetime."""
        if not date_str:
            return None
        try:
            clean = str(date_str).strip()[:10]
            dt = datetime.strptime(clean, "%Y-%m-%d")
            if is_end:
                return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            return None

    @classmethod
    def generate_inventory_report(cls, region: str = None, commodity: str = None) -> Path:
        """
        Exports full regional inventory status with stock and buffer analysis.
        Supports filtering by region and commodity.
        """
        db = get_db()
        and_clauses = []
        if region and region.strip() and region.strip().upper() != "ALL":
            and_clauses.append({"region": {"$regex": f"^{re.escape(region.strip())}$", "$options": "i"}})
        if commodity and commodity.strip() and commodity.strip().upper() != "ALL":
            comm_clean = commodity.strip()
            and_clauses.append({"$or": [
                {"commodity": {"$regex": f"^{re.escape(comm_clean)}$", "$options": "i"}},
                {"commodity_code": comm_clean.upper()}
            ]})

        filter_query = {"$and": and_clauses} if and_clauses else {}
        items = list(db.inventory.find(filter_query, {"_id": 0}).sort([("region", 1), ("commodity", 1)]))

        rows = []
        for it in items:
            cur_stock = float(it.get("current_stock", 0.0))
            buf_stock = float(it.get("buffer_stock", 0.0))
            cap = float(it.get("capacity", 0.0))
            
            if cur_stock < buf_stock:
                status = "CRITICAL SHORTAGE"
            elif cur_stock < (buf_stock * 1.5):
                status = "LOW BUFFER"
            else:
                status = "SUFFICIENT STOCK"

            cov_ratio = round(cur_stock / (buf_stock + 1e-5), 2)
            last_up = it.get("last_updated") or it.get("updated_at")
            if isinstance(last_up, datetime):
                up_str = last_up.strftime("%Y-%m-%d %H:%M:%S")
            else:
                up_str = str(last_up or "N/A")

            rows.append({
                "Commodity Name": it.get("commodity", ""),
                "Depot District": it.get("region", ""),
                "Current Warehouse Stock (kg)": round(cur_stock, 1),
                "Target Safety Buffer (kg)": round(buf_stock, 1),
                "Buffer Coverage Ratio": f"{cov_ratio}x",
                "Inventory Stock Status": status,
                "Last Stock Verification": up_str
            })

        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=[
                "Commodity Name", "Depot District", "Current Warehouse Stock (kg)",
                "Target Safety Buffer (kg)", "Buffer Coverage Ratio",
                "Inventory Stock Status", "Last Stock Verification"
            ])

        tag = f"_{region.strip()}" if region and region.strip().upper() != "ALL" else ""
        filename = f"inventory_report{tag}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = REPORTS_DIR / filename

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Warehouse Inventory", index=False)

        cls._apply_excel_formatting(filepath, "Warehouse Inventory", "Warehouse Inventory Status")
        logger.info(f"Generated inventory report: {filepath} ({len(df)} records)")
        return filepath

    @classmethod
    def generate_distribution_report(
        cls,
        region: str = None,
        commodity: str = None,
        start_date: str = None,
        end_date: str = None,
        risk_level: str = None
    ) -> Path:
        """
        Exports grain distribution transaction log with date range, commodity, and district filtering.
        """
        db = get_db()
        and_clauses = []
        if region and region.strip() and region.strip().upper() != "ALL":
            and_clauses.append({"region": {"$regex": f"^{re.escape(region.strip())}$", "$options": "i"}})
        if commodity and commodity.strip() and commodity.strip().upper() != "ALL":
            comm_clean = commodity.strip()
            and_clauses.append({"$or": [
                {"commodity": {"$regex": f"^{re.escape(comm_clean)}$", "$options": "i"}},
                {"commodity_code": comm_clean.upper()}
            ]})
        if risk_level and risk_level.strip() and risk_level.strip().upper() != "ALL":
            and_clauses.append({"risk_level": risk_level.strip().upper()})

        dt_start = cls._parse_date_bound(start_date, is_end=False)
        dt_end = cls._parse_date_bound(end_date, is_end=True)
        if dt_start or dt_end:
            time_filter = {}
            if dt_start:
                time_filter["$gte"] = dt_start
            if dt_end:
                time_filter["$lte"] = dt_end
            and_clauses.append({"timestamp": time_filter})

        filter_query = {"$and": and_clauses} if and_clauses else {}
        txns = list(db.transactions.find(filter_query, {"_id": 0}).sort("timestamp", -1))

        rows = []
        for t in txns:
            ts = t.get("timestamp")
            if isinstance(ts, datetime):
                utc_str = ts.strftime("%Y-%m-%d %H:%M:%S")
                local_str = ts.strftime("%d-%b-%Y %I:%M %p")
            else:
                utc_str = str(ts or "N/A")
                local_str = utc_str

            rows.append({
                "Transaction ID": t.get("transaction_id", ""),
                "Beneficiary ID": t.get("beneficiary_id", ""),
                "Ration Shop ID": t.get("ration_shop_id", ""),
                "Commodity Distributed": t.get("commodity", ""),
                "Quantity Distributed (kg)": round(float(t.get("quantity", 0.0)), 1),
                "Depot District": t.get("region", ""),
                "Distribution Time (UTC)": utc_str,
                "Local Formatted Time": local_str,
                "Risk Classification": t.get("risk_level", "LOW"),
                "Isolation Forest Score": round(float(t.get("anomaly_score", 0.0)), 4),
                "Processing Status": t.get("processing_status", "COMPLETED"),
                "Officer Review Decision": t.get("review_decision") or t.get("review_status") or "PENDING_REVIEW",
                "Reviewing Officer": t.get("reviewed_by") or "Unreviewed",
                "Audit Rationale / Reasons": t.get("review_reason") or t.get("review_comments") or t.get("reason", "")
            })

        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=[
                "Transaction ID", "Beneficiary ID", "Ration Shop ID", "Commodity Distributed",
                "Quantity Distributed (kg)", "Depot District", "Distribution Time (UTC)",
                "Local Formatted Time", "Risk Classification", "Isolation Forest Score",
                "Processing Status", "Officer Review Decision", "Reviewing Officer", "Audit Rationale / Reasons"
            ])

        tag = f"_{region.strip()}" if region and region.strip().upper() != "ALL" else ""
        filename = f"distribution_report{tag}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = REPORTS_DIR / filename

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Transactions Ledger", index=False)

        cls._apply_excel_formatting(filepath, "Transactions Ledger", "PDS Distribution Transactions Ledger")
        logger.info(f"Generated distribution report: {filepath} ({len(df)} records)")
        return filepath

    @classmethod
    def generate_fraud_report(
        cls,
        region: str = None,
        commodity: str = None,
        risk_level: str = None,
        status: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> Path:
        """
        Exports flagged suspicious transactions, Isolation Forest anomaly scores,
        and officer audit review decisions with commodity, district, and date filtering.
        """
        db = get_db()
        and_clauses = []
        if region and region.strip() and region.strip().upper() != "ALL":
            and_clauses.append({"region": {"$regex": f"^{re.escape(region.strip())}$", "$options": "i"}})
        if commodity and commodity.strip() and commodity.strip().upper() != "ALL":
            comm_clean = commodity.strip()
            and_clauses.append({"$or": [
                {"commodity": {"$regex": f"^{re.escape(comm_clean)}$", "$options": "i"}},
                {"commodity_code": comm_clean.upper()}
            ]})
        if risk_level and risk_level.strip() and risk_level.strip().upper() != "ALL":
            and_clauses.append({"risk_level": risk_level.strip().upper()})
        if status and status.strip() and status.strip().upper() != "ALL":
            st = status.strip().upper()
            if st in ["VERIFIED_LEGITIMATE", "APPROVED_GENUINE"]:
                and_clauses.append({"status": {"$in": ["VERIFIED_LEGITIMATE", "APPROVED_GENUINE", "DISMISSED_FALSE_POSITIVE"]}})
            elif st in ["CONFIRMED_IRREGULARITY", "FLAGGED_FRAUD"]:
                and_clauses.append({"status": {"$in": ["CONFIRMED_IRREGULARITY", "FLAGGED_FRAUD"]}})
            elif st == "REVIEWED":
                and_clauses.append({"status": {"$in": ["REVIEWED", "VERIFIED_LEGITIMATE", "CONFIRMED_IRREGULARITY", "RESOLVED", "APPROVED_GENUINE", "FLAGGED_FRAUD"]}})
            elif st == "PENDING_REVIEW":
                and_clauses.append({"status": {"$in": ["PENDING_REVIEW", "PENDING", "NEW", None]}})
            else:
                and_clauses.append({"status": st})

        dt_start = cls._parse_date_bound(start_date, is_end=False)
        dt_end = cls._parse_date_bound(end_date, is_end=True)
        if dt_start or dt_end:
            time_filter = {}
            if dt_start:
                time_filter["$gte"] = dt_start
            if dt_end:
                time_filter["$lte"] = dt_end
            and_clauses.append({"$or": [{"created_at": time_filter}, {"timestamp": time_filter}]})

        filter_query = {"$and": and_clauses} if and_clauses else {}
        alerts = list(db.fraud_alerts.find(filter_query, {"_id": 0}).sort("created_at", -1))

        rows = []
        for a in alerts:
            score = float(a.get("anomaly_score", 0.0))
            score_interp = a.get("score_interpretation")
            if not score_interp:
                if score >= 0.0:
                    score_interp = "Normal distribution range"
                elif score >= -0.10:
                    score_interp = "Mild statistical deviation"
                else:
                    score_interp = "Severe outlier in tree ensemble"

            created_at = a.get("created_at") or a.get("timestamp")
            flagged_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created_at, datetime) else str(created_at or "N/A")
            reviewed_at = a.get("reviewed_at")
            rev_str = reviewed_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(reviewed_at, datetime) else (str(reviewed_at) if reviewed_at else "Pending Review")

            quota = a.get("entitled_quota")
            quota_val = round(float(quota), 1) if isinstance(quota, (int, float)) else str(quota or "N/A")

            ratio = a.get("quantity_to_quota_ratio")
            ratio_str = f"{float(ratio):.1f}x" if isinstance(ratio, (int, float)) else (str(ratio) if ratio else "N/A")

            rows.append({
                "Alert Transaction ID": a.get("transaction_id", ""),
                "Beneficiary ID": a.get("beneficiary_id", ""),
                "Ration Shop ID": a.get("ration_shop_id", ""),
                "Commodity": a.get("commodity", ""),
                "Withdrawn Quantity (kg)": round(float(a.get("quantity", 0.0)), 1),
                "Depot District": a.get("region", ""),
                "Risk Classification": a.get("risk_level", "HIGH"),
                "Isolation Forest Decision Score": round(score, 4),
                "Outlier Score Interpretation": score_interp,
                "Card Entitlement Cap (kg)": quota_val,
                "Quantity / Quota Ratio": ratio_str,
                "Explainable Detection Reasons": a.get("reason", ""),
                "Audit Review Status": a.get("status", "PENDING_REVIEW"),
                "Official Officer Decision": a.get("review_decision") or a.get("status") or "PENDING",
                "Reviewing Officer ID": a.get("reviewed_by") or "Unassigned",
                "Officer Audit Justification": a.get("review_reason") or a.get("comments") or "",
                "Review Timestamp": rev_str,
                "Alert Logged Timestamp": flagged_str
            })

        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=[
                "Alert Transaction ID", "Beneficiary ID", "Ration Shop ID", "Commodity", "Withdrawn Quantity (kg)",
                "Depot District", "Risk Classification", "Isolation Forest Decision Score",
                "Outlier Score Interpretation", "Card Entitlement Cap (kg)", "Quantity / Quota Ratio",
                "Explainable Detection Reasons", "Audit Review Status", "Official Officer Decision",
                "Reviewing Officer ID", "Officer Audit Justification", "Review Timestamp", "Alert Logged Timestamp"
            ])

        tag = f"_{region.strip()}" if region and region.strip().upper() != "ALL" else ""
        filename = f"fraud_anomaly_report{tag}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = REPORTS_DIR / filename

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Flagged Anomalies", index=False)

        cls._apply_excel_formatting(filepath, "Flagged Anomalies", "Fraud & Statistical Anomaly Audit Log")
        logger.info(f"Generated fraud report: {filepath} ({len(df)} records)")
        return filepath

    @classmethod
    def generate_predictions_report(cls, region: str = None, commodity: str = None) -> Path:
        """
        Exports ML demand predictions and calculated procurement recommendations.
        Reads saved prediction audit records from db.predictions.
        If no audit records exist for the selected filter, runs the active ML pipeline to generate fresh records.
        """
        from backend.services.ml_service import MLService
        db = get_db()

        and_clauses = []
        if region and region.strip() and region.strip().upper() != "ALL":
            and_clauses.append({"region": {"$regex": f"^{re.escape(region.strip())}$", "$options": "i"}})
        if commodity and commodity.strip() and commodity.strip().upper() != "ALL":
            comm_clean = commodity.strip()
            and_clauses.append({"$or": [
                {"commodity": {"$regex": f"^{re.escape(comm_clean)}$", "$options": "i"}},
                {"commodity_code": comm_clean.upper()}
            ]})

        filter_query = {"$and": and_clauses} if and_clauses else {}
        preds = list(db.predictions.find(filter_query, {"_id": 0}).sort("created_at", -1))

        # If no audit records exist in predictions collection for this filter, compute from live inventory & ML pipeline
        if not preds:
            inv_items = list(db.inventory.find(filter_query, {"_id": 0}))
            now = datetime.utcnow()
            for it in inv_items:
                com = it.get("commodity", "Rice")
                reg = it.get("region", "Chennai")
                stk = float(it.get("current_stock", 3800.0))
                buf = float(it.get("buffer_stock", 500.0))
                
                try:
                    p = MLService.predict_demand({
                        "commodity": com,
                        "region": reg,
                        "month": now.month,
                        "year": now.year,
                        "current_stock": stk,
                        "safety_stock": buf,
                        "previous_demand": stk * 1.1,
                        "beneficiary_count": 12500,
                        "is_custom_scenario": False
                    }, save_audit=False)
                    preds.append(p)
                except Exception as e:
                    logger.warning(f"Could not generate prediction for {com}/{reg}: {e}")

        rows = []
        for p in preds:
            bd = p.get("calculation_breakdown", {})
            created = p.get("created_at")
            if isinstance(created, datetime):
                created_str = created.strftime("%Y-%m-%d %H:%M:%S")
            else:
                created_str = str(created or "N/A")

            # Extract 95% confidence range if available
            conf = p.get("confidence_range", {})
            if isinstance(conf, dict) and conf.get("available"):
                conf_str = conf.get("formatted_range") or f"{conf.get('lower_bound_kg', conf.get('lower_bound', 0)):,.1f} - {conf.get('upper_bound_kg', conf.get('upper_bound', 0)):,.1f} kg"
            else:
                conf_str = "Not Available"

            # Extract actual vs predicted comparison if available
            act = p.get("actual_comparison", {})
            if isinstance(act, dict) and act.get("has_actual_data"):
                act_str = f"{float(act.get('actual_demand_kg', 0.0)):,.1f}"
                var_str = f"{float(act.get('variance_kg', 0.0)):+,.1f}"
            else:
                act_str = "Pending Ledger"
                var_str = "N/A"

            # Historical baseline
            base_val = bd.get("baseline_demand") or bd.get("baseline_momentum_kg") or p.get("previous_demand") or "N/A"
            if isinstance(base_val, (int, float)):
                base_str = round(float(base_val), 1)
            else:
                base_str = base_val

            # Seasonal multiplier
            s_mult = bd.get("seasonal_multiplier") or p.get("seasonal_multiplier")
            s_lbl = bd.get("seasonal_label") or ""
            if s_mult:
                mult_display = f"{float(s_mult):.2f}x" + (f" ({s_lbl})" if s_lbl else "")
            else:
                mult_display = "1.00x"

            rows.append({
                "Commodity": p.get("commodity", ""),
                "Commodity Code": p.get("commodity_code", ""),
                "Depot District": p.get("region", ""),
                "Forecast Month": p.get("month", datetime.utcnow().month),
                "Forecast Year": p.get("year", datetime.utcnow().year),
                "Registered Cardholders": p.get("beneficiary_count", 12500),
                "Historical Baseline (kg)": base_str,
                "Seasonal Weighting": mult_display,
                "Predicted Monthly Demand (kg)": round(float(p.get("predicted_demand", 0.0)), 1),
                "Current Warehouse Stock (kg)": round(float(p.get("current_stock", 0.0)), 1),
                "Target Safety Buffer (kg)": round(float(p.get("safety_stock", 0.0)), 1),
                "Gross Requirement (kg)": round(float(bd.get("gross_requirement", float(p.get("predicted_demand", 0.0)) + float(p.get("safety_stock", 0.0)))), 1),
                "Net Detected Shortage (kg)": round(float(p.get("shortage", 0.0)), 1),
                "Recommended Procurement (kg)": round(float(p.get("recommended_procurement", 0.0)), 1),
                "95% Confidence Interval": conf_str,
                "Actual Demand Recorded (kg)": act_str,
                "Forecast Variance (kg)": var_str,
                "Inventory Coverage Status": p.get("status", "SUFFICIENT"),
                "Procurement Formula": bd.get("procurement_formula", "max(0, (Predicted Demand + Buffer) - Stock)"),
                "Production ML Model": p.get("model_used", "Linear Regression"),
                "Data Source": p.get("data_source", "DATABASE_BACKED"),
                "Prediction Generated At": created_str
            })

        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=[
                "Commodity", "Commodity Code", "Depot District", "Forecast Month", "Forecast Year",
                "Registered Cardholders", "Historical Baseline (kg)", "Seasonal Weighting",
                "Predicted Monthly Demand (kg)", "Current Warehouse Stock (kg)", "Target Safety Buffer (kg)",
                "Gross Requirement (kg)", "Net Detected Shortage (kg)", "Recommended Procurement (kg)",
                "95% Confidence Interval", "Actual Demand Recorded (kg)", "Forecast Variance (kg)",
                "Inventory Coverage Status", "Procurement Formula", "Production ML Model",
                "Data Source", "Prediction Generated At"
            ])

        tag = f"_{region.strip()}" if region and region.strip().upper() != "ALL" else ""
        filename = f"demand_predictions_report{tag}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = REPORTS_DIR / filename

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Demand Forecast", index=False)

        cls._apply_excel_formatting(filepath, "Demand Forecast", "ML Demand Forecast & Procurement Recommendations")
        logger.info(f"Generated predictions report: {filepath} ({len(df)} records)")
        return filepath
