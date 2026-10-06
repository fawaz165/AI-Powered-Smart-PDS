import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)


class Config:
    """Base Configuration for AI-Powered Smart PDS"""
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.getenv("SECRET_KEY", "smart_pds_default_secret_key_2026")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    PORT = int(os.getenv("PORT", 5000))

    # MongoDB Settings
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/smart_pds_db")
    DB_NAME = os.getenv("DB_NAME", "smart_pds_db")

    # Directory Paths
    MODEL_DIR = BASE_DIR / os.getenv("MODEL_DIR", "ml/saved_models")
    DATA_DIR = BASE_DIR / "ml" / "data"
    REPORTS_DIR = BASE_DIR / "reports"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Thresholds for Inventory Alert System
    CRITICAL_STOCK_THRESHOLD_KG = 500.0
    EXCESS_STOCK_MULTIPLIER = 1.5  # If stock > 1.5x predicted demand, flag excess
    
    # Supported Essential Commodities
    SUPPORTED_COMMODITIES = ["Rice", "Wheat", "Sugar", "Dal"]
    
    # Supported Regions
    SUPPORTED_REGIONS = ["Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli"]


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    DB_NAME = "smart_pds_test_db"
    MONGO_URI = os.getenv("TEST_MONGO_URI", "mongodb://localhost:27017/smart_pds_test_db")


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
