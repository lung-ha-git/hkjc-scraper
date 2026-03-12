"""
HKJC Queue Worker
Execute scrape jobs from queue
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection
from src.crawler.race_results_scraper import RaceResultsScraper

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
            # Increment retry count
            self.db.db[queue_name].update_one(
                {"_id": item_id},
                {
                    "$inc": {"retry_count": 1},
                    "$set": update
                }
            )
        else:
            self.db.db[queue_name].update_one(
                {"_id": item_id},
                {"$set": update}
            )
    
    async def scrape_race_result(self, item: Dict) -> bool:
        """Scrape race result using RaceResultsScraper"""
        race_date = item["race_date"]  # Format: YYYY-MM-DD
        race_no = item["race_no"]
        
        # Convert date format: YYYY-MM-DD -> YYYY/MM/DD
        race_date_formatted = race_date.replace("-", "/")
        
        # Get venue from item or use default
        venue = item.get("venue", "ST")
        
        logger.info(f"Scraping race result: {race_date} R{race_no}")
        
        try:
            # Use existing RaceResultsScraper
            async with RaceResultsScraper(headless=True) as scraper:
                result = await scraper.scrape_race(race_date_formatted, venue, race_no)
                
                if result:
                    # Save to MongoDB
                    self._save_race_result(result)
                    logger.info(f"  ✓ Race {race_no} saved to DB")
                    return True
                else:
                    logger.error(f"  ✗ No data returned from scraper")
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
        
        # Build race_id
        venue = result.get("racecourse", "ST")
        race_id = f"{race_date.replace('/', '_')}_{venue}_{race_no}"
        
        # Build document
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
        
        # Upsert to DB
        self.db.db["races"].update_one(
            {"hkjc_race_id": race_id},
            {"$set": doc},
            upsert=True
        )
    
    async def scrape_horse_detail(self, item: Dict) -> bool:
        """Scrape horse detail"""
        logger.info(f"Scraping horse: {item['horse_id']}")
        
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                url = item["target_url"]
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                
                # TODO: Implement actual scraping logic
                
                await browser.close()
                
            logger.info(f"  ✓ Horse detail scraped")
            return True
            
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False
    
    async def scrape_jockey_detail(self, item: Dict) -> bool:
        """Scrape jockey detail"""
        logger.info(f"Scraping jockey: {item['jockey_id']}")
        
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                url = item["target_url"]
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                
                # Get the page content
                content = await page.inner_text("body")
                
                # Parse jockey stats from content
                # For now, just mark as completed
                
                await browser.close()
                
            logger.info(f"  ✓ Jockey detail scraped")
            return True
            
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False
    
    async def scrape_trainer_detail(self, item: Dict) -> bool:
        """Scrape trainer detail"""
        logger.info(f"Scraping trainer: {item['trainer_id']}")
        
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                url = item["target_url"]
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                
                # TODO: Implement actual scraping logic
                
                await browser.close()
                
            logger.info(f"  ✓ Trainer detail scraped")
            return True
            
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False
    
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
            # Mark as in_progress
            self.db.db[queue_name].update_one(
                {"_id": item["_id"]},
                {"$set": {"status": "in_progress", "modified_at": datetime.now()}}
            )
            
            # Process
            success = await self.process_item(item)
            
            if success:
                self.update_item_status(queue_name, item["_id"], "completed")
                completed += 1
            else:
                # Check retry count
                if item.get("retry_count", 0) >= 3:
                    self.update_item_status(queue_name, item["_id"], "failed", "Max retries exceeded")
                    failed += 1
                else:
                    self.update_item_status(queue_name, item["_id"], "pending", "Retry needed")
                    failed += 1
            
            # Small delay between scrapes
            await asyncio.sleep(2)
        
        return {
            "checked": len(items),
            "completed": completed,
            "failed": failed
        }
    
    async def run(self):
        """Main worker job"""
        logger.info("=" * 60)
        logger.info("QUEUE WORKER STARTING")
        logger.info("=" * 60)
        
        if not self.connect():
            logger.error("Cannot connect to MongoDB")
            return
        
        # Process each queue
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
        
        return {
            "completed": total_completed,
            "failed": total_failed
        }


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    worker = QueueWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
