"""
HKJC Sync Scheduler
Daily job: Check fixtures, add queue items for races with published data
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Schedule scrape jobs based on fixtures"""
    
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
    
    async def check_racecard_published(self, date: str, venue: str) -> bool:
        """Check if racecard has data published"""
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Format: 2026/03/15
            date_formatted = date.replace("-", "/")
            url = f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date_formatted}&Racecourse={venue}"
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                
                content = await page.inner_text("body")
                has_data = "沒有相關資料" not in content and len(content) > 800
                
            except Exception as e:
                logger.warning(f"Error checking {url}: {e}")
                has_data = False
            finally:
                await browser.close()
            
            return has_data
    
    def get_pending_fixtures(self, days_ahead: int = 14, days_back: int = 7) -> List[Dict]:
        """Get fixtures that haven't been processed yet
        
        Args:
            days_ahead: Number of days ahead to check (default 14)
            days_back: Number of past days to check (default 7)
        """
        from datetime import date
        
        today = date.today().isoformat()
        future_date = (date.today() + timedelta(days=days_ahead)).isoformat()
        past_date = (date.today() - timedelta(days=days_back)).isoformat()
        
        return list(self.db.db["fixtures"].find({
            "scrape_status": "pending",
            "date": {"$gte": past_date, "$lte": future_date}
        }).sort("date", 1))
    
    def add_race_queue_item(self, fixture: Dict, race_no: int) -> str:
        """Add a race to race_queue"""
        now = datetime.now()
        
        # Scheduled for next day 09:00
        scheduled_time = (now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        
        item = {
            "type": "race_result",
            "target_url": f"https://racing.hkjc.com/zh-hk/racing/information/English/Racing/LocalResults.aspx?RaceDate={fixture['date']}",
            "race_date": fixture['date'],
            "venue": fixture['venue'],
            "race_no": race_no,
            "scheduled_scrape_time": scheduled_time,
            "status": "pending",
            "retry_count": 0,
            "created_at": now,
            "modified_at": now
        }
        
        result = self.db.db["race_queue"].insert_one(item)
        return str(result.inserted_id)
    
    def add_horse_queue_item(self, fixture: Dict, horse_id: str) -> str:
        """Add a horse to scrape_queue"""
        now = datetime.now()
        
        scheduled_time = (now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        
        item = {
            "type": "horse_detail",
            "target_url": f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={horse_id}",
            "horse_id": horse_id,
            "race_date": fixture['date'],
            "scheduled_scrape_time": scheduled_time,
            "status": "pending",
            "retry_count": 0,
            "created_at": now,
            "modified_at": now
        }
        
        result = self.db.db["scrape_queue"].insert_one(item)
        return str(result.inserted_id)
    
    def add_jockey_queue_item(self, jockey_id: str) -> str:
        """Add a jockey to jockey_queue"""
        now = datetime.now()
        
        scheduled_time = (now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        
        item = {
            "type": "jockey_detail",
            "target_url": f"https://racing.hkjc.com/zh-hk/local/information/jockeyprofile?jockeyid={jockey_id}&season=Current",
            "jockey_id": jockey_id,
            "scheduled_scrape_time": scheduled_time,
            "status": "pending",
            "retry_count": 0,
            "created_at": now,
            "modified_at": now
        }
        
        result = self.db.db["jockey_queue"].insert_one(item)
        return str(result.inserted_id)
    
    def add_trainer_queue_item(self, trainer_id: str) -> str:
        """Add a trainer to trainer_queue"""
        now = datetime.now()
        
        scheduled_time = (now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        
        item = {
            "type": "trainer_detail",
            "target_url": f"https://racing.hkjc.com/zh-hk/local/information/trainerprofile?trainerid={trainer_id}&season=Current",
            "trainer_id": trainer_id,
            "scheduled_scrape_time": scheduled_time,
            "status": "pending",
            "retry_count": 0,
            "created_at": now,
            "modified_at": now
        }
        
        result = self.db.db["trainer_queue"].insert_one(item)
        return str(result.inserted_id)
    
    def get_existing_jockeys(self) -> List[str]:
        """Get list of existing jockey IDs"""
        return [doc["jockey_id"] for doc in self.db.db["jockeys"].find({}, {"jockey_id": 1})]
    
    def get_existing_trainers(self) -> List[str]:
        """Get list of existing trainer IDs"""
        return [doc["trainer_id"] for doc in self.db.db["trainers"].find({}, {"trainer_id": 1})]
    
    def get_existing_horses(self) -> List[str]:
        """Get list of existing horse IDs"""
        return [doc["hkjc_horse_id"] for doc in self.db.db["horses"].find({}, {"hkjc_horse_id": 1})]
    
    async def process_fixture(self, fixture: Dict) -> Dict:
        """Process a single fixture"""
        from datetime import date
        
        date_str = fixture["date"]
        venue = fixture["venue"]
        race_count = fixture["race_count"]
        
        logger.info(f"Checking {date_str} ({venue}) - {race_count} races...")
        
        # Determine if this is a past date or future date
        fixture_date = date.fromisoformat(date_str)
        is_past = fixture_date < date.today()
        
        has_data = False
        
        if is_past:
            # For past dates, check if we already have the races in DB
            existing_races = self.db.db["races"].count_documents({
                "race_date": date_str.replace("-", "/")
            })
            has_data = existing_races >= race_count
            logger.info(f"  Past date: {existing_races}/{race_count} races in DB")
        else:
            # For future dates, check if racecard is published
            has_data = await self.check_racecard_published(date_str, venue)
        
        if not has_data:
            # For past dates with no data in DB, we should scrape them!
            if is_past and existing_races == 0:
                logger.info(f"  Past date with no data - will scrape!")
                # Set has_data to True so we add to queue
                has_data = True
            else:
                logger.info(f"  No data available, skipping")
                
                # For past dates with no data, mark as "needs_sync" to retry later
                if is_past:
                    self.db.db["fixtures"].update_one(
                        {"_id": fixture["_id"]},
                        {"$set": {
                            "scrape_status": "needs_sync",
                            "modified_at": datetime.now()
                        }}
                    )
                
                return {"status": "no_data", "race_count": 0}
        
        # Past dates with data in DB - already scraped, skip
        if is_past and existing_races >= race_count:
            logger.info(f"  Already scraped ({existing_races} races in DB), skipping")
            self.db.db["fixtures"].update_one(
                {"_id": fixture["_id"]},
                {"$set": {
                    "scrape_status": "completed",
                    "modified_at": datetime.now()
                }}
            )
            return {"status": "already_done", "race_count": existing_races}
        
        logger.info(f"  Racecard published! Adding queue items...")
        
        # Add race queue items (one per race)
        race_items = 0
        for race_no in range(1, race_count + 1):
            self.add_race_queue_item(fixture, race_no)
            race_items += 1
        
        # Get existing horses and add to scrape queue
        horse_ids = self.get_existing_horses()
        horse_items = 0
        for horse_id in horse_ids[:20]:  # Limit to 20 for now
            # Check if already queued recently
            existing = self.db.db["scrape_queue"].find_one({
                "horse_id": horse_id,
                "status": "pending"
            })
            if not existing:
                self.add_horse_queue_item(fixture, horse_id)
                horse_items += 1
        
        # Add jockey queue items (unique jockeys)
        jockey_ids = self.get_existing_jockeys()
        jockey_items = 0
        for jockey_id in jockey_ids[:10]:  # Limit to top 10 for now
            # Check if already queued today
            existing = self.db.db["jockey_queue"].find_one({
                "jockey_id": jockey_id,
                "status": "pending"
            })
            if not existing:
                self.add_jockey_queue_item(jockey_id)
                jockey_items += 1
        
        # Add trainer queue items
        trainer_ids = self.get_existing_trainers()
        trainer_items = 0
        for trainer_id in trainer_ids[:10]:
            existing = self.db.db["trainer_queue"].find_one({
                "trainer_id": trainer_id,
                "status": "pending"
            })
            if not existing:
                self.add_trainer_queue_item(trainer_id)
                trainer_items += 1
        
        # Update fixture status
        self.db.db["fixtures"].update_one(
            {"_id": fixture["_id"]},
            {"$set": {
                "scrape_status": "queued",
                "modified_at": datetime.now()
            }}
        )
        
        return {
            "status": "queued",
            "race_items": race_items,
            "horse_items": horse_items,
            "jockey_items": jockey_items,
            "trainer_items": trainer_items
        }
    
    async def run(self):
        """Main sync job"""
        logger.info("=" * 60)
        logger.info("SYNC SCHEDULER STARTING")
        logger.info("=" * 60)
        
        if not self.connect():
            logger.error("Cannot connect to MongoDB")
            return
        
        # Get pending fixtures
        fixtures = self.get_pending_fixtures()
        logger.info(f"Found {len(fixtures)} pending fixtures")
        
        # Process each fixture
        results = []
        for fixture in fixtures:
            result = await self.process_fixture(fixture)
            results.append({
                "date": fixture["date"],
                "venue": fixture["venue"],
                **result
            })
            
            # Small delay between checks
            await asyncio.sleep(1)
        
        # Summary
        total_races = sum(r.get("race_items", 0) for r in results)
        total_horses = sum(r.get("horse_items", 0) for r in results)
        total_jockeys = sum(r.get("jockey_items", 0) for r in results)
        total_trainers = sum(r.get("trainer_items", 0) for r in results)
        
        logger.info("=" * 60)
        logger.info("SYNC SCHEDULER COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Fixtures processed: {len(results)}")
        logger.info(f"Race queue items: {total_races}")
        logger.info(f"Horse queue items: {total_horses}")
        logger.info(f"Jockey queue items: {total_jockeys}")
        logger.info(f"Trainer queue items: {total_trainers}")
        
        self.disconnect()
        
        return {
            "fixtures": len(results),
            "race_items": total_races,
            "horse_items": total_horses,
            "jockey_items": total_jockeys,
            "trainer_items": total_trainers
        }


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    scheduler = SyncScheduler()
    await scheduler.run()


if __name__ == "__main__":
    asyncio.run(main())
