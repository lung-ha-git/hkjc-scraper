"""
HKJC Racing Database Connection
MongoDB connection and setup
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """MongoDB connection manager"""
    
    def __init__(self, connection_string: str = None, 
                 db_name: str = None):
        # Load from config if not specified
        if connection_string is None:
            from config.settings import MONGODB_URI
            connection_string = MONGODB_URI
        if db_name is None:
            from config.settings import MONGODB_DB_NAME
            db_name = MONGODB_DB_NAME
        self.connection_string = connection_string
        self.db_name = db_name
        self.client: Optional[MongoClient] = None
        self.db = None
        
    def connect(self) -> bool:
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(
                self.connection_string,
                serverSelectionTimeoutMS=5000
            )
            # Verify connection
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            logger.info(f"✅ Connected to MongoDB: {self.db_name}")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close connection"""
        if self.client:
            self.client.close()
            logger.info("🔌 MongoDB connection closed")
    
    def get_collection(self, collection_name: str):
        """Get a collection"""
        if self.db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self.db[collection_name]
    
    @property
    def races(self):
        return self.get_collection("races")
    
    @property
    def horses(self):
        return self.get_collection("horses")
    
    @property
    def jockeys(self):
        return self.get_collection("jockeys")
    
    @property
    def trainers(self):
        return self.get_collection("trainers")
    
    @property
    def raw_results(self):
        return self.get_collection("raw_results")
    
    def create_indexes(self):
        """Create database indexes"""
        if self.db is None:
            raise RuntimeError("Database not connected")
        
        # Races indexes
        self.races.create_index("race_id", unique=True)
        self.races.create_index([("date", DESCENDING)])
        self.races.create_index([("venue", ASCENDING), ("race_no", ASCENDING)])
        
        # Horses indexes
        self.horses.create_index("horse_id", unique=True)
        self.horses.create_index("horse_name")
        
        # Jockeys indexes
        self.jockeys.create_index("jockey_id", unique=True)
        self.jockeys.create_index("name")
        
        # Trainers indexes
        self.trainers.create_index("trainer_id", unique=True)
        self.trainers.create_index("name")
        
        # Raw results indexes
        self.raw_results.create_index([("date", DESCENDING)])
        self.raw_results.create_index([("scraped_at", DESCENDING)])
        
        logger.info("✅ Database indexes created")
    
    def get_stats(self) -> dict:
        """Get database statistics"""
        if self.db is None:
            return {"error": "Not connected"}
        
        return {
            "races": self.races.count_documents({}),
            "horses": self.horses.count_documents({}),
            "jockeys": self.jockeys.count_documents({}),
            "trainers": self.trainers.count_documents({}),
            "raw_results": self.raw_results.count_documents({})
        }


# Singleton instance
db_connection = DatabaseConnection()


def get_db():
    """Get database connection"""
    if db_connection.db is None:
        db_connection.connect()
    return db_connection
