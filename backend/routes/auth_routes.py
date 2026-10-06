from flask import Blueprint, request, jsonify
from backend.services.auth_service import AuthService, token_required
from backend.database.mongo import get_db
from backend.models.user import UserModel
from backend.utils.logger import logger

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def login():
    """User login endpoint."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password are required"}), 400

    result = AuthService.authenticate(username, password)
    if not result:
        return jsonify({"status": "error", "message": "Invalid username or password"}), 401

    logger.info(f"User '{username}' logged in successfully.")
    return jsonify({
        "status": "success",
        "message": "Authentication successful",
        "data": result
    }), 200


@auth_bp.route("/me", methods=["GET"])
@token_required
def get_current_user():
    """Returns currently authenticated user profile."""
    return jsonify({
        "status": "success",
        "user": getattr(request, "user", {})
    }), 200


@auth_bp.route("/register", methods=["POST"])
def register():
    """Allows creating additional officer/admin users."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role", "officer")
    email = data.get("email")
    full_name = data.get("full_name")

    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password required"}), 400

    db = get_db()
    if db.users.find_one({"username": username}):
        return jsonify({"status": "error", "message": "User already exists"}), 409

    user_doc = UserModel.create_user_doc(username, password, role, email, full_name)
    db.users.insert_one(user_doc)
    logger.info(f"New user registered: {username}")
    return jsonify({
        "status": "success",
        "message": f"User {username} registered successfully"
    }), 201
