"""
HKJC Queue Worker
Execute scrape jobs from queue

Note: Jockey/Trainer data is handled by Phase 5 ranking scraper
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection
from src.crawler.race_results_scraper import RaceResultsScraper
from src.crawler.horse_detail_scraper import HorseDetailScraper

logger = logging.getLogger(__name__)


class QueueWorker:
    """Process queue items"""
    
    def __init__(self):
        self.db = None
        
    def connect(self):
        """Connect to MongoDB"""
        self.db = DatabaseConnection()
        return self.db.connect()
    
    def disconnect(self):
        """Disconnect from MongoDB"""
        if self.db:
            self.db.disconnect()
    
    def get_pending_items(self, queue_name: str, limit: int = 50) -> List[Dict]:
        """Get pending items that are ready to scrape"""
        now = datetime.now()
        
        return list(self.db.db[queue_name].find({
            "status": "pending",
            "scheduled_scrape_time": {"$lte": now}
        }).limit(limit))
    
    def update_item_status(self, queue_name: str, item_id: str, status: str, error: str = None):
        """Update item status"""
        update = {
            "status": status,
            "modified_at": datetime.now()
        }
        
        if error:
            update["error"] = error
            
        if status == "failed":
            self.db.db[queue_name].update_one(
                {"_id": item_id},
                {"$inc": {"retry_count": 1}, "$set": update}
            )
        else:
            self.db.db[queue_name].update_one(
                {"_id": item_id},
                {"$set": update}
            )
    
    async def scrape_race_result(self, item: Dict) -> bool:
        """Scrape race result using RaceResultsScraper"""
        race_date = item["race_date"]
        race_no = item["race_no"]
        race_date_formatted = race_date.replace("-", "/")
        venue = item.get("venue", "ST")
        
        logger.info(f"Scraping race result: {race_date} R{race_no}")
        
        try:
            async with RaceResultsScraper(headless=True) as scraper:
                result = await scraper.scrape_race(race_date_formatted, venue, race_no)
                
                if result:
                    self._save_race_result(result)
                    logger.info(f"  ✓ Race {race_no} saved to DB")
                    return True
                else:
                    logger.error(f"  ✗ No data returned")
                    return False
            
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False
    
    def _save_race_result(self, result: Dict):
        """Save race result to MongoDB"""
        if not result:
            return
        
        race_date = result.get("race_date", "")
        race_no = result.get("race_no", "")
        venue = result.get("racecourse", "ST")
        race_id = f"{race_date.replace('/', '_')}_{venue}_{race_no}"
        
        doc = {
            "hkjc_race_id": race_id,
            "race_date": race_date,
            "venue": venue,
            "race_no": str(race_no),
            "race_id_num": result.get("metadata", {}).get("race_id_num"),
            "class": result.get("metadata", {}).get("class"),
            "distance": result.get("metadata", {}).get("distance"),
            "track_condition": result.get("metadata", {}).get("track_condition"),
            "prize": result.get("metadata", {}).get("prize"),
            "results": result.get("results", []),
            "payout": result.get("payouts", {}),
            "incidents": result.get("incidents", []),
            "created_at": datetime.now(),
            "modified_at": datetime.now()
        }
        
        self.db.db["races"].update_one(
            {"hkjc_race_id": race_id},
            {"$set": doc},
            upsert=True
        )
    
    async def scrape_horse_detail(self, item: Dict) -> bool:
        """Scrape horse detail using HorseDetailScraper"""
        horse_id = item.get("horse_id")
        
        if not horse_id:
            logger.error(f"  ✗ No horse_id in item")
            return False
        
        logger.info(f"Scraping horse detail: {horse_id}")
        
        try:
            scraper = HorseDetailScraper(headless=True)
            result = await scraper.scrape_horse_detail(horse_id)
            
            if result:
                self._save_horse_detail(horse_id, result)
                logger.info(f"  ✓ Horse {horse_id} saved to DB")
                return True
            else:
                logger.error(f"  ✗ No data returned")
                return False
            
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False
    
    def _save_horse_detail(self, horse_id: str, data: Dict):
        """Save horse detail to MongoDB"""
        if not data:
            return
        
        update_data = {
            "modified_at": datetime.now()
        }
        
        # Map scraped data to MongoDB fields
        field_map = {
            "name": "name",
            "country": "country_of_origin",
            "age": "age",
            "color": "color",
            "sex": "sex",
            "import_type": "import_type",
            "trainer": "trainer",
            "owner": "owner",
            "sire": "sire",
            "dam": "dam",
        }
        
        for scraper_field, db_field in field_map.items():
            if scraper_field in data:
                update_data[db_field] = data[scraper_field]
        
        # Handle pedigree
        if "pedigree" in data and data["pedigree"]:
            pedigree = data["pedigree"]
            if "sire" in pedigree:
                update_data["sire"] = pedigree["sire"]
            if "dam" in pedigree:
                update_data["dam"] = pedigree["dam"]
            if "damsire" in pedigree:
                update_data["maternal_grand_sire"] = pedigree["damsire"]
        
        # Handle stats
        if "stats" in data and data["stats"]:
            stats = data["stats"]
            if "season_prize_money" in stats:
                update_data["season_prize"] = stats["season_prize_money"]
            if "total_prize_money" in stats:
                update_data["total_prize"] = stats["total_prize_money"]
        
        self.db.db["horses"].update_one(
            {"hkjc_horse_id": horse_id},
            {"$set": update_data},
            upsert=True
        )
    
    async def scrape_jockey_detail(self, item: Dict) -> bool:
        """Mark jockey as updated - Phase 5 ranking scraper already has data"""
        jockey_id = item.get("jockey_id")
        
        if not jockey_id:
            logger.error(f"  ✗ No jockey_id in item")
            return False
        
        logger.info(f"Jockey {jockey_id}: data from Phase 5 ranking scraper")
        return True
    
    async def scrape_trainer_detail(self, item: Dict) -> bool:
        """Mark trainer as updated - Phase 5 ranking scraper already has data"""
        trainer_id = item.get("trainer_id")
        
        if not trainer_id:
            logger.error(f"  ✗ No trainer_id in item")
            return False
        
        logger.info(f"Trainer {trainer_id}: data from Phase 5 ranking scraper")
        return True
    
    async def process_item(self, item: Dict) -> bool:
        """Process a single queue item"""
        item_type = item.get("type")
        
        scrapers = {
            "race_result": self.scrape_race_result,
            "horse_detail": self.scrape_horse_detail,
            "jockey_detail": self.scrape_jockey_detail,
            "trainer_detail": self.scrape_trainer_detail
        }
        
        scraper = scrapers.get(item_type)
        if not scraper:
            logger.warning(f"Unknown type: {item_type}")
            return False
        
        return await scraper(item)
    
    async def process_queue(self, queue_name: str) -> Dict:
        """Process all pending items in a queue"""
        items = self.get_pending_items(queue_name)
        
        if not items:
            return {"checked": 0, "completed": 0, "failed": 0}
        
        logger.info(f"Processing {len(items)} items from {queue_name}...")
        
        completed = 0
        failed = 0
        
        for item in items:
            self.db.db[queue_name].update_one(
                {"_id": item["_id"]},
                {"$set": {"status": "in_progress", "modified_at": datetime.now()}}
            )
            
            success = await self.process_item(item)
            
            if success:
                self.update_item_status(queue_name, item["_id"], "completed")
                completed += 1
            else:
                if item.get("retry_count", 0) >= 3:
                    self.update_item_status(queue_name, item["_id"], "failed", "Max retries")
                    failed += 1
                else:
                    self.update_item_status(queue_name, item["_id"], "pending", "Retry")
                    failed += 1
            
            await asyncio.sleep(2)
        
        return {"checked": len(items), "completed": completed, "failed": failed}
    
    async def run(self):
        """Main worker job"""
        logger.info("=" * 60)
        logger.info("QUEUE WORKER STARTING")
        logger.info("=" * 60)
        
        if not self.connect():
            logger.error("Cannot connect to MongoDB")
            return
        
        queues = ["race_queue", "scrape_queue", "jockey_queue", "trainer_queue"]
        
        total_completed = 0
        total_failed = 0
        
        for queue_name in queues:
            result = await self.process_queue(queue_name)
            total_completed += result["completed"]
            total_failed += result["failed"]
            logger.info(f"{queue_name}: {result}")
        
        logger.info("=" * 60)
        logger.info("QUEUE WORKER COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total completed: {total_completed}")
        logger.info(f"Total failed: {total_failed}")
        
        self.disconnect()
        
        return {"completed": total_completed, "failed": total_failed}


async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    worker = QueueWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
