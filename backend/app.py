import os
import sys
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.config import Config
from backend.database.mongo import Database
from backend.services.ml_service import MLService
from backend.utils.logger import logger

# Import Blueprints
from backend.routes.auth_routes import auth_bp
from backend.routes.beneficiary_routes import beneficiary_bp
from backend.routes.commodity_routes import commodity_bp
from backend.routes.inventory_routes import inventory_bp
from backend.routes.transaction_routes import transaction_bp
from backend.routes.ml_routes import ml_bp
from backend.routes.report_routes import report_bp


def create_app(config_class=Config):
    """Application factory for AI-Powered Smart PDS."""
    frontend_dir = BASE_DIR / "frontend"
    app = Flask(
        __name__,
        static_folder=str(frontend_dir),
        static_url_path=""
    )
    
    app.config.from_object(config_class)
    CORS(app)

    # Initialize Database connection
    try:
        Database(uri=app.config["MONGO_URI"], db_name=app.config["DB_NAME"])
    except Exception as e:
        logger.error(f"Database initialization warning: {e}")

    # Eager load ML models
    try:
        MLService.load_models()
    except Exception as e:
        logger.warning(f"ML models could not be eager loaded: {e}")

    # Register API Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(beneficiary_bp)
    app.register_blueprint(commodity_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(transaction_bp)
    app.register_blueprint(ml_bp)
    app.register_blueprint(report_bp)

    # Health check endpoint
    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "healthy",
            "service": "AI-Powered Smart Public Distribution System",
            "version": "1.0.0"
        }), 200

    # Frontend serving routes
    @app.route("/")
    def serve_index():
        return send_from_directory(str(frontend_dir), "index.html")

    @app.route("/<path:filename>")
    def serve_frontend_file(filename):
        target = frontend_dir / filename
        if target.exists() and target.is_file():
            return send_from_directory(str(frontend_dir), filename)
        # Fallback to index.html for SPA-style routing if file not found
        return send_from_directory(str(frontend_dir), "index.html")

    # Global Error Handlers
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "API resource not found"}), 404
        return send_from_directory(str(frontend_dir), "index.html"), 200

    @app.errorhandler(400)
    def bad_request_error(error):
        return jsonify({"status": "error", "message": "Bad request"}), 400

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return jsonify({
            "status": "error",
            "message": "An internal server error occurred. Please contact the administrator."
        }), 500

    return app


app = create_app()

if __name__ == "__main__":
    logger.info(f"Starting Smart PDS Server on http://localhost:{Config.PORT}")
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
