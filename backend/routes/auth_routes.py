import os
from flask import Blueprint, request, jsonify, current_app
from backend.services.auth_service import AuthService, token_required, role_required
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
    """Allows creating user accounts with role-based administrative authorization."""
    db = get_db()
    total_users = db.users.count_documents({})

    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    role = str(data.get("role", "officer")).strip().lower()
    email = data.get("email")
    full_name = data.get("full_name")
    region = data.get("region")
    ration_shop_id = data.get("ration_shop_id")

    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password required"}), 400

    # Authorization guard:
    # 1. When no users exist (initial deployment), unrestricted admin registration is NOT permitted.
    #    Initial registration strictly requires a valid BOOTSTRAP_ADMIN_KEY from the environment,
    #    or direct initialization via the CLI seed script (`python backend/database/seed_db.py`).
    # 2. When users already exist, registering any new user account strictly requires an Administrator JWT token.
    if total_users == 0:
        bootstrap_key = os.getenv("BOOTSTRAP_ADMIN_KEY", "").strip()
        req_bootstrap_key = (request.headers.get("X-Bootstrap-Key") or data.get("bootstrap_key") or "").strip()
        if not bootstrap_key or req_bootstrap_key != bootstrap_key:
            return jsonify({
                "status": "error",
                "message": "Authentication required. Initial setup requires a valid BOOTSTRAP_ADMIN_KEY header/token, or run the CLI seed script ('python backend/database/seed_db.py')."
            }), 401
    else:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.split(" ")[1] if auth_header.startswith("Bearer ") else request.args.get("token")

        if not token:
            return jsonify({
                "status": "error",
                "message": "Authentication required. Only administrators can register new user accounts."
            }), 401

        payload = AuthService.verify_token(token)
        if not payload:
            return jsonify({"status": "error", "message": "Invalid or expired authentication token"}), 401

        caller_role = str(payload.get("role", "")).strip().lower()
        if caller_role != "admin":
            return jsonify({
                "status": "error",
                "message": "Forbidden. Only users with the 'admin' role can register user accounts."
            }), 403

    if db.users.find_one({"username": username}):
        return jsonify({"status": "error", "message": "User already exists"}), 409

    user_doc = UserModel.create_user_doc(
        username=username,
        password=password,
        role=role,
        email=email,
        full_name=full_name,
        region=region,
        ration_shop_id=ration_shop_id
    )
    db.users.insert_one(user_doc)
    logger.info(f"New user registered: {username} (Role: {role})")
    return jsonify({
        "status": "success",
        "message": f"User {username} registered successfully"
    }), 201
