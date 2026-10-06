import hmac
import hashlib
import json
import base64
import time
from functools import wraps
from flask import request, jsonify
from backend.config import Config
from backend.database.mongo import get_db
from backend.models.user import UserModel
from backend.utils.logger import logger


class AuthService:
    """Manages user authentication and lightweight tamper-proof signature tokens."""

    @classmethod
    def generate_token(cls, user_data: dict, expires_in_sec: int = 86400) -> str:
        """Generates a base64 encoded signed JSON Web-style token."""
        payload = {
            "sub": user_data["username"],
            "role": user_data.get("role", "admin"),
            "exp": int(time.time()) + expires_in_sec
        }
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        b64_payload = base64.urlsafe_b64encode(payload_bytes).decode('utf-8').rstrip('=')
        
        signature = hmac.new(
            Config.SECRET_KEY.encode('utf-8'),
            b64_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"{b64_payload}.{signature}"

    @classmethod
    def verify_token(cls, token: str) -> dict:
        """Verifies HMAC signature and token expiration."""
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None
            b64_payload, signature = parts[0], parts[1]
            
            expected_sig = hmac.new(
                Config.SECRET_KEY.encode('utf-8'),
                b64_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected_sig, signature):
                return None
            
            # Add padding
            rem = len(b64_payload) % 4
            if rem:
                b64_payload += '=' * (4 - rem)
            
            payload = json.loads(base64.urlsafe_b64decode(b64_payload.encode('utf-8')).decode('utf-8'))
            if payload.get("exp", 0) < time.time():
                return None
            return payload
        except Exception as e:
            logger.warning(f"Token verification error: {e}")
            return None

    @classmethod
    def authenticate(cls, username, password):
        """Validates credentials against MongoDB users."""
        db = get_db()
        user = db.users.find_one({"username": username.strip().lower()})
        if not user:
            return None
        if UserModel.verify_password(user["password_hash"], password):
            token = cls.generate_token(user)
            return {
                "token": token,
                "username": user["username"],
                "role": user.get("role", "admin"),
                "full_name": user.get("full_name", user["username"].capitalize())
            }
        return None


def token_required(f):
    """Decorator to enforce API authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        elif request.args.get("token"):
            token = request.args.get("token")

        if not token:
            return jsonify({"status": "error", "message": "Authentication token is missing"}), 401

        payload = AuthService.verify_token(token)
        if not payload:
            return jsonify({"status": "error", "message": "Token is invalid or expired"}), 401

        request.user = payload
        return f(*args, **kwargs)
    return decorated
