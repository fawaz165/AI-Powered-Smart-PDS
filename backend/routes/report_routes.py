from flask import Blueprint, jsonify, send_file, request
from backend.services.report_service import ReportService
from backend.utils.logger import logger

report_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@report_bp.route("/inventory", methods=["GET"])
def download_inventory_report():
    """Generates and triggers download for the Warehouse Inventory Excel report with optional filters."""
    try:
        region = request.args.get("region", "").strip()
        commodity = request.args.get("commodity", "").strip()
        filepath = ReportService.generate_inventory_report(region=region, commodity=commodity)
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filepath.name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        logger.error(f"Failed to generate inventory report: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@report_bp.route("/distribution", methods=["GET"])
def download_distribution_report():
    """Generates and triggers download for the Distribution Transactions Excel report with optional filters."""
    try:
        region = request.args.get("region", "").strip()
        commodity = request.args.get("commodity", "").strip()
        start_date = request.args.get("start_date", "").strip()
        end_date = request.args.get("end_date", "").strip()
        risk_level = request.args.get("risk_level", "").strip()

        filepath = ReportService.generate_distribution_report(
            region=region,
            commodity=commodity,
            start_date=start_date,
            end_date=end_date,
            risk_level=risk_level
        )
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filepath.name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        logger.error(f"Failed to generate distribution report: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@report_bp.route("/fraud", methods=["GET"])
def download_fraud_report():
    """Generates and triggers download for the Fraud/Anomaly Review Excel report with optional filters."""
    try:
        region = request.args.get("region", "").strip()
        risk_level = request.args.get("risk_level", "").strip()
        status = request.args.get("status", "").strip()
        start_date = request.args.get("start_date", "").strip()
        end_date = request.args.get("end_date", "").strip()

        filepath = ReportService.generate_fraud_report(
            region=region,
            risk_level=risk_level,
            status=status,
            start_date=start_date,
            end_date=end_date
        )
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filepath.name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        logger.error(f"Failed to generate fraud report: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@report_bp.route("/predictions", methods=["GET"])
def download_predictions_report():
    """Generates and triggers download for the ML Demand Predictions Excel report with optional filters."""
    try:
        region = request.args.get("region", "").strip()
        commodity = request.args.get("commodity", "").strip()
        filepath = ReportService.generate_predictions_report(region=region, commodity=commodity)
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filepath.name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        logger.error(f"Failed to generate predictions report: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
