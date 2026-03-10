"""
Scraping Queue Manager
Manages horse scraping queue with completeness tracking
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from src.database.connection import DatabaseConnection


def get_now() -> str:
    """Get current UTC timestamp"""
    return datetime.now(timezone.utc).isoformat()


class ScrapingQueue:
    """Manages scraping queue with completeness tracking"""
    
    def __init__(self):
        self.db = None
    
    def connect(self):
        """Connect to database"""
        self.db = DatabaseConnection()
        return self.db.connect()
    
    def disconnect(self):
        """Disconnect from database"""
        if self.db:
            self.db.disconnect()
    
    def init_queue(self, horse_ids: List[str]):
        """Initialize queue with horse IDs"""
        if not self.db:
            self.connect()
        
        now = get_now()
        
        for horse_id in horse_ids:
            # Check if already exists
            existing = self.db.db.scraping_queue.find_one({"hkjc_horse_id": horse_id})
            
            if not existing:
                # Insert new
                self.db.db.scraping_queue.insert_one({
                    "hkjc_horse_id": horse_id,
                    "status": "pending",
                    "data_status": {},
                    "scrape_count": 0,
                    "last_updated": now,
                    "created_at": now,
                    "modified_at": now,
                    "error": None
                })
    
    def get_next_pending(self, limit: int = 10) -> List[str]:
        """Get next pending horse IDs"""
        if not self.db:
            self.connect()
        
        pending = list(self.db.db.scraping_queue.find(
            {"status": "pending"}
        ).limit(limit))
        
        return [p["hkjc_horse_id"] for p in pending]
    
    def mark_in_progress(self, horse_id: str):
        """Mark horse as in progress"""
        if not self.db:
            self.connect()
        
        now = get_now()
        self.db.db.scraping_queue.update_one(
            {"hkjc_horse_id": horse_id},
            {
                "$set": {
                    "status": "in_progress",
                    "modified_at": now
                }
            }
        )
    
    def update_data_status(self, horse_id: str, data_counts: Dict[str, int]):
        """Update data completeness status"""
        if not self.db:
            self.connect()
        
        now = get_now()
        self.db.db.scraping_queue.update_one(
            {"hkjc_horse_id": horse_id},
            {
                "$set": {
                    "data_status": data_counts,
                    "status": "completed",
                    "scrape_count": {"$inc": 1},
                    "modified_at": now,
                    "last_updated": now
                },
                "$setOnInsert": {"created_at": now}
            }
        )
    
    def mark_failed(self, horse_id: str, error: str):
        """Mark horse as failed"""
        if not self.db:
            self.connect()
        
        now = get_now()
        self.db.db.scraping_queue.update_one(
            {"hkjc_horse_id": horse_id},
            {
                "$set": {
                    "status": "failed",
                    "error": error,
                    "modified_at": now
                }
            }
        )
    
    def get_completeness(self, horse_id: str) -> Dict:
        """Get completeness status for a horse"""
        if not self.db:
            self.connect()
        
        return self.db.db.scraping_queue.find_one(
            {"hkjc_horse_id": horse_id},
            {"_id": 0, "data_status": 1, "status": 1}
        )
    
    def get_all_completeness(self) -> Dict[str, Dict]:
        """Get completeness for all horses"""
        if not self.db:
            self.connect()
        
        all_data = {}
        for doc in self.db.db.scraping_queue.find():
            all_data[doc["hkjc_horse_id"]] = {
                "status": doc.get("status"),
                "data_status": doc.get("data_status", {}),
                "scrape_count": doc.get("scrape_count", 0)
            }
        
        return all_data
    
    def reset_failed(self):
        """Reset failed horses to pending"""
        if not self.db:
            self.connect()
        
        self.db.db.scraping_queue.update_many(
            {"status": "failed"},
            {"$set": {"status": "pending", "modified_at": get_now()}}
        )
    
    def reset_all(self):
        """Reset all to pending"""
        if not self.db:
            self.connect()
        
        self.db.db.scraping_queue.update_many(
            {},
            {"$set": {"status": "pending", "modified_at": get_now()}}
        )
    
    def get_stats(self) -> Dict:
        """Get queue statistics"""
        if not self.db:
            self.connect()
        
        stats = {
            "total": self.db.db.scraping_queue.count_documents({}),
            "pending": self.db.db.scraping_queue.count_documents({"status": "pending"}),
            "in_progress": self.db.db.scraping_queue.count_documents({"status": "in_progress"}),
            "completed": self.db.db.scraping_queue.count_documents({"status": "completed"}),
            "failed": self.db.db.scraping_queue.count_documents({"status": "failed"}),
        }
        
        return stats


# Helper functions for adding timestamps to any collection

def add_timestamps(doc: Dict, is_new: bool = True) -> Dict:
    """Add created_at and modified_at timestamps to a document"""
    now = get_now()
    
    if is_new:
        doc["created_at"] = now
    doc["modified_at"] = now
    
    return doc


def update_with_timestamps(collection, query: Dict, update: Dict):
    """Update with automatic timestamps"""
    now = get_now()
    
    # Add modified_at to $set
    if "$set" not in update:
        update["$set"] = {}
    update["$set"]["modified_at"] = now
    
    collection.update_one(query, update)


# Singleton instance
_queue: Optional[ScrapingQueue] = None

def get_scraping_queue() -> ScrapingQueue:
    """Get or create scraping queue singleton"""
    global _queue
    if _queue is None:
        _queue = ScrapingQueue()
    return _queue
