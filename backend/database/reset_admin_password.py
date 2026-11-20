"""
Safe utility to reset ONLY the demo admin password without touching other users,
beneficiaries, commodities, inventory, or transaction records.
"""
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.database.mongo import Database
from backend.models.user import UserModel
from backend.utils.logger import logger


def reset_admin_password(new_password: str = "admin123"):
    """Resets or creates the admin account with the specified password."""
    db_inst = Database()
    db = db_inst.db

    admin_user = db.users.find_one({"username": "admin"})
    if not admin_user:
        logger.info("Admin account does not exist. Creating demo admin account...")
        user_doc = UserModel.create_user_doc(
            username="admin",
            password=new_password,
            role="admin",
            email="admin@smartpds.gov.in",
            full_name="PDS Chief Administrator"
        )
        db.users.insert_one(user_doc)
        logger.info("Demo admin account created successfully.")
        print(f"[SUCCESS] Admin account created with password '{new_password}'.")
    else:
        logger.info("Resetting password for existing admin user...")
        db.users.update_one(
            {"username": "admin"},
            {"$set": {"password_hash": generate_password_hash(new_password)}}
        )
        logger.info("Admin password reset successfully.")
        print(f"[SUCCESS] Admin password successfully reset to '{new_password}'.")


if __name__ == "__main__":
    password_arg = sys.argv[1] if len(sys.argv) > 1 else "admin123"
    reset_admin_password(password_arg)
