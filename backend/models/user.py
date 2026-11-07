from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class UserModel:
    """User representation for Admin, District Officers, and FPS Dealers."""
    ROLES = ["admin", "officer", "dealer"]

    @staticmethod
    def create_user_doc(username, password, role="admin", email=None, full_name=None, region=None, ration_shop_id=None):
        role_clean = role.strip().lower() if role else "admin"
        return {
            "username": username.strip().lower(),
            "password_hash": generate_password_hash(password),
            "role": role_clean,
            "region": region.strip() if region else None,
            "ration_shop_id": ration_shop_id.strip().upper() if ration_shop_id else None,
            "email": email.strip().lower() if email else f"{username}@smartpds.gov.in",
            "full_name": full_name or username.capitalize(),
            "created_at": datetime.utcnow(),
            "is_active": True
        }

    @staticmethod
    def verify_password(stored_hash, candidate_password):
        return check_password_hash(stored_hash, candidate_password)
