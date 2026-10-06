from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class UserModel:
    """User representation for Admin and Ration Officers."""
    @staticmethod
    def create_user_doc(username, password, role="admin", email=None, full_name=None):
        return {
            "username": username.strip().lower(),
            "password_hash": generate_password_hash(password),
            "role": role,
            "email": email.strip().lower() if email else f"{username}@smartpds.gov.in",
            "full_name": full_name or username.capitalize(),
            "created_at": datetime.utcnow(),
            "is_active": True
        }

    @staticmethod
    def verify_password(stored_hash, candidate_password):
        return check_password_hash(stored_hash, candidate_password)
