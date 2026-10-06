import pymongo
from pymongo import ASCENDING, DESCENDING
from backend.config import Config
from backend.utils.logger import logger


class Database:
    """Singleton MongoDB wrapper providing collection access and index management."""
    _instance = None
    _client = None
    _db = None

    def __new__(cls, uri: str = None, db_name: str = None):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            uri = uri or Config.MONGO_URI
            db_name = db_name or Config.DB_NAME
            try:
                cls._client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=4000)
                # Verify connection
                cls._client.admin.command("ping")
                cls._db = cls._client[db_name]
                logger.info(f"MongoDB connected successfully to database: {db_name}")
                cls._create_indexes(cls._db)
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB at {uri}: {e}")
                raise e
        return cls._instance

    @classmethod
    def _create_indexes(cls, db):
        """Creates compound and unique indexes on frequently queried fields."""
        try:
            # Users: unique username
            db.users.create_index([("username", ASCENDING)], unique=True)
            db.users.create_index([("email", ASCENDING)], unique=True, sparse=True)

            # Beneficiaries: unique beneficiary_id, index on ration_card_number and region
            db.beneficiaries.create_index([("beneficiary_id", ASCENDING)], unique=True)
            db.beneficiaries.create_index([("ration_card_number", ASCENDING)], unique=True)
            db.beneficiaries.create_index([("region", ASCENDING)])
            db.beneficiaries.create_index([("ration_card_type", ASCENDING)])

            # Commodities: unique code/name
            db.commodities.create_index([("name", ASCENDING)], unique=True)
            db.commodities.create_index([("commodity_code", ASCENDING)], unique=True)

            # Inventory: unique (commodity, region) pair
            db.inventory.create_index([("commodity", ASCENDING), ("region", ASCENDING)], unique=True)

            # Transactions: transaction_id, beneficiary_id, ration_shop_id, timestamp
            db.transactions.create_index([("transaction_id", ASCENDING)], unique=True)
            db.transactions.create_index([("beneficiary_id", ASCENDING)])
            db.transactions.create_index([("ration_shop_id", ASCENDING)])
            db.transactions.create_index([("timestamp", DESCENDING)])
            db.transactions.create_index([("commodity", ASCENDING)])

            # Predictions: commodity, region, timestamp
            db.predictions.create_index([("commodity", ASCENDING), ("region", ASCENDING)])
            db.predictions.create_index([("created_at", DESCENDING)])

            # Fraud Alerts: transaction_id, risk_level, status
            db.fraud_alerts.create_index([("transaction_id", ASCENDING)], unique=True)
            db.fraud_alerts.create_index([("risk_level", ASCENDING)])
            db.fraud_alerts.create_index([("status", ASCENDING)])

            # Ration Shops: shop_id, region
            db.ration_shops.create_index([("shop_id", ASCENDING)], unique=True)
            db.ration_shops.create_index([("region", ASCENDING)])

            logger.info("MongoDB indexes verified and created successfully.")
        except Exception as e:
            logger.warning(f"Note during index creation: {e}")

    @property
    def client(self):
        return self._client

    @property
    def db(self):
        return self._db

    # Direct collection properties for clean querying
    @property
    def users(self):
        return self._db.users

    @property
    def beneficiaries(self):
        return self._db.beneficiaries

    @property
    def commodities(self):
        return self._db.commodities

    @property
    def inventory(self):
        return self._db.inventory

    @property
    def transactions(self):
        return self._db.transactions

    @property
    def predictions(self):
        return self._db.predictions

    @property
    def fraud_alerts(self):
        return self._db.fraud_alerts

    @property
    def ration_shops(self):
        return self._db.ration_shops


# Easy accessor function
def get_db():
    return Database().db


def get_db_instance():
    return Database()
