from flask import Blueprint, jsonify, send_file
from backend.services.report_service import ReportService
from backend.utils.logger import logger

report_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@report_bp.route("/inventory", methods=["GET"])
def download_inventory_report():
    """Generates and triggers download for the Inventory Excel report."""
    try:
        filepath = ReportService.generate_inventory_report()
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
    """Generates and triggers download for the Distribution Transactions Excel report."""
    try:
        filepath = ReportService.generate_distribution_report()
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
    """Generates and triggers download for the Fraud/Anomaly Review Excel report."""
    try:
        filepath = ReportService.generate_fraud_report()
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
    """Generates and triggers download for the ML Predictions Excel report."""
    try:
        filepath = ReportService.generate_predictions_report()
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filepath.name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        logger.error(f"Failed to generate predictions report: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
