"""
Database Setup Script
Initialize MongoDB collections and indexes
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import DatabaseConnection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_database():
    """Initialize database"""
    logger.info("🚀 Setting up HKJC database...")
    
    db = DatabaseConnection()
    
    # Connect
    if not db.connect():
        logger.error("❌ Failed to connect to MongoDB")
        logger.info("💡 Make sure MongoDB is running:")
        logger.info("   macOS: brew services start mongodb-community")
        logger.info("   Linux: sudo systemctl start mongod")
        return False
    
    try:
        # Create indexes
        db.create_indexes()
        
        # Verify collections exist
        collections = db.db.list_collection_names()
        logger.info(f"📊 Collections: {collections}")
        
        logger.info("✅ Database setup complete!")
        logger.info(f"📁 Database: {db.db_name}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        return False
    finally:
        db.disconnect()


if __name__ == "__main__":
    success = setup_database()
    sys.exit(0 if success else 1)
