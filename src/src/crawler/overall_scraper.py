"""
HKJC Overall Scraper - Phase 3 Implementation
Parallel scraping with activity logging

Workflow:
1. Queue all horses for scraping
2. Parallel scrape horse details + extract race URLs
3. Deduplicate race URLs
4. Parallel scrape all races

Author: OpenClaw Agent
Date: 2026-03-09
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Set
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.crawler.hkjc_precise_scraper import HKJCPreciseScraper
from src.crawler.race_results_scraper import RaceResultsScraper
from src.database.connection import DatabaseConnection


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ActivityLog:
    """Activity logging for scraping operations"""
    timestamp: str
    phase: str
    action: str
    target_id: str
    status: str
    details: Dict
    error_message: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


class ScrapingActivityLogger:
    """Logger for all scraping activities"""
    
    def __init__(self, db: DatabaseConnection):
        self.db = db
        self.collection = "scraping_activity_log"
    
    def log(self, phase: str, action: str, target_id: str, 
            status: str, details: Dict = None, error: str = ""):
        """Log a scraping activity"""
        log_entry = ActivityLog(
            timestamp=datetime.now().isoformat(),
            phase=phase,
            action=action,
            target_id=target_id,
            status=status,
            details=details or {},
            error_message=error
        )
        
        self.db.db[self.collection].insert_one(log_entry.to_dict())
        
        # Also log to console
        msg = f"[{phase}] {action} - {target_id}: {status}"
        if error:
            logger.error(f"{msg} - Error: {error}")
        else:
            logger.info(msg)
    
    def get_summary(self, phase: str = None) -> Dict:
        """Get activity summary"""
        match = {"phase": phase} if phase else {}
        
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }}
        ]
        
        results = list(self.db.db[self.collection].aggregate(pipeline))
        return {r["_id"]: r["count"] for r in results}


class OverallScraper:
    """
    Overall scraper implementing Phase 3 workflow
    
    Phase 1: Queue all horses
    Phase 2: Parallel scrape horses + extract race URLs
    Phase 3: Parallel scrape all unique races
    """
    
    def __init__(self, max_concurrent: int = 3, headless: bool = True):
        self.max_concurrent = max_concurrent
        self.headless = headless
        self.db = DatabaseConnection()
        self.activity_logger = None
        
        # Tracking sets
        self.processed_horses: Set[str] = set()
        self.race_urls: Dict[str, Dict] = {}  # race_id -> race_info
    
    async def run(self, horse_ids: List[str]):
        """
        Run complete scraping workflow
        
        Args:
            horse_ids: List of HKJC horse IDs to scrape
        """
        print("\n" + "=" * 80)
        print("🏇 HKJC OVERALL SCRAPER - PHASE 3")
        print("=" * 80)
        
        if not self.db.connect():
            logger.error("Failed to connect to MongoDB")
            return
        
        self.activity_logger = ScrapingActivityLogger(self.db)
        
        try:
            # Phase 1: Initialize queue
            await self._phase1_queue_horses(horse_ids)
            
            # Phase 2: Scrape horses and extract race URLs
            await self._phase2_scrape_horses(horse_ids)
            
            # Phase 3: Scrape all unique races
            await self._phase3_scrape_races()
            
            # Final summary
            await self._print_summary()
            
        finally:
            self.db.disconnect()
    
    async def _phase1_queue_horses(self, horse_ids: List[str]):
        """Phase 1: Initialize scraping queue for all horses"""
        print(f"\n📋 PHASE 1: Queueing {len(horse_ids)} horses")
        print("-" * 80)
        
        for horse_id in horse_ids:
            # Check if already queued
            existing = self.db.db["scraper_queue"].find_one({
                "type": "horse",
                "id": horse_id
            })
            
            if existing:
                self.activity_logger.log(
                    phase="phase1",
                    action="queue_horse",
                    target_id=horse_id,
                    status="skipped",
                    details={"reason": "already_queued"}
                )
            else:
                self.db.db["scraper_queue"].insert_one({
                    "type": "horse",
                    "id": horse_id,
                    "status": "pending",
                    "priority": 1,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                })
                
                self.activity_logger.log(
                    phase="phase1",
                    action="queue_horse",
                    target_id=horse_id,
                    status="queued"
                )
        
        print(f"✅ {len(horse_ids)} horses queued")
    
    async def _phase2_scrape_horses(self, horse_ids: List[str]):
        """Phase 2: Parallel scrape horses and extract race URLs"""
        print(f"\n🐴 PHASE 2: Scraping {len(horse_ids)} horses (max {self.max_concurrent} concurrent)")
        print("-" * 80)
        
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def scrape_with_limit(horse_id: str):
            async with semaphore:
                return await self._scrape_single_horse(horse_id)
        
        # Process all horses
        tasks = [scrape_with_limit(hid) for hid in horse_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count results
        success = sum(1 for r in results if not isinstance(r, Exception))
        errors = sum(1 for r in results if isinstance(r, Exception))
        
        print(f"✅ Completed: {success} success, {errors} errors")
        print(f"📊 Discovered {len(self.race_urls)} unique race URLs")
    
    async def _scrape_single_horse(self, horse_id: str) -> bool:
        """Scrape a single horse and extract race URLs"""
        try:
            # Update status to processing
            self.db.db["scraper_queue"].update_one(
                {"type": "horse", "id": horse_id},
                {"$set": {"status": "processing", "updated_at": datetime.now().isoformat()}}
            )
            
            # Scrape horse
            async with HKJCPreciseScraper(headless=self.headless) as horse_scraper:
                horse_data = await horse_scraper.scrape_horse(horse_id)
                
                # Save horse data
                await horse_scraper.save_to_mongodb(horse_data)
                
                # Extract race URLs from race history
                race_count = 0
                for race in horse_data.get("race_history", []):
                    race_id = self._extract_race_id(race)
                    if race_id and race_id not in self.race_urls:
                        self.race_urls[race_id] = {
                            "race_id": race_id,
                            "source_horses": [horse_id],
                            "date": race.get("date"),
                            "extracted_from": horse_id
                        }
                        race_count += 1
                    elif race_id:
                        # Add horse to existing race sources
                        if horse_id not in self.race_urls[race_id]["source_horses"]:
                            self.race_urls[race_id]["source_horses"].append(horse_id)
                
                # Update status to done
                self.db.db["scraper_queue"].update_one(
                    {"type": "horse", "id": horse_id},
                    {"$set": {"status": "done", "updated_at": datetime.now().isoformat()}}
                )
                
                self.activity_logger.log(
                    phase="phase2",
                    action="scrape_horse",
                    target_id=horse_id,
                    status="success",
                    details={
                        "races_discovered": race_count,
                        "total_races": len(self.race_urls)
                    }
                )
                
                return True
                
        except Exception as e:
            # Update status to error
            self.db.db["scraper_queue"].update_one(
                {"type": "horse", "id": horse_id},
                {"$set": {"status": "error", "error": str(e), "updated_at": datetime.now().isoformat()}}
            )
            
            self.activity_logger.log(
                phase="phase2",
                action="scrape_horse",
                target_id=horse_id,
                status="error",
                error=str(e)
            )
            
            raise
    
    def _extract_race_id(self, race: Dict) -> str:
        """Extract unique race ID from race history entry"""
        # Race history format: date + race_no
        date = race.get("date", "").replace("/", "-")
        race_no = race.get("race_no", "")
        
        if date and race_no:
            return f"{date}_{race_no}"
        return None
    
    async def _phase3_scrape_races(self):
        """Phase 3: Parallel scrape all unique races"""
        race_list = list(self.race_urls.values())
        
        print(f"\n🏇 PHASE 3: Scraping {len(race_list)} unique races")
        print("-" * 80)
        
        if not race_list:
            print("⚠️ No races to scrape")
            return
        
        # Queue all races
        for race_info in race_list:
            race_id = race_info["race_id"]
            
            # Check if already scraped
            existing = self.db.db["races"].find_one({"_id": race_id})
            if existing:
                self.activity_logger.log(
                    phase="phase3",
                    action="queue_race",
                    target_id=race_id,
                    status="skipped",
                    details={"reason": "already_exists"}
                )
                continue
            
            # Add to queue
            self.db.db["scraper_queue"].insert_one({
                "type": "race",
                "id": race_id,
                "status": "pending",
                "source_horses": race_info["source_horses"],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            })
        
        # Scrape races in parallel
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def scrape_race_with_limit(race_info: Dict):
            async with semaphore:
                return await self._scrape_single_race(race_info)
        
        tasks = [scrape_race_with_limit(r) for r in race_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success = sum(1 for r in results if not isinstance(r, Exception))
        errors = sum(1 for r in results if isinstance(r, Exception))
        
        print(f"✅ Completed: {success} success, {errors} errors")
    
    async def _scrape_single_race(self, race_info: Dict) -> bool:
        """Scrape a single race"""
        race_id = race_info["race_id"]
        
        try:
            # Parse race_id to get parameters
            # Format: YYYY-MM-DD_RaceNo
            parts = race_id.split("_")
            if len(parts) != 2:
                raise ValueError(f"Invalid race_id format: {race_id}")
            
            # This needs to be mapped to actual race date format
            # For now, we'll use placeholder logic
            race_date = parts[0].replace("-", "/")
            race_no = int(parts[1])
            
            # TODO: Map to actual racecourse (ST/HV)
            racecourse = "ST"  # Default to Sha Tin
            
            # Update status
            self.db.db["scraper_queue"].update_one(
                {"type": "race", "id": race_id},
                {"$set": {"status": "processing", "updated_at": datetime.now().isoformat()}}
            )
            
            # Scrape race
            async with RaceResultsScraper(headless=self.headless) as race_scraper:
                race_data = await race_scraper.scrape_race(race_date, racecourse, race_no)
                await race_scraper.save_to_mongodb(race_data)
            
            # Update status
            self.db.db["scraper_queue"].update_one(
                {"type": "race", "id": race_id},
                {"$set": {"status": "done", "updated_at": datetime.now().isoformat()}}
            )
            
            self.activity_logger.log(
                phase="phase3",
                action="scrape_race",
                target_id=race_id,
                status="success",
                details={"date": race_date, "race_no": race_no}
            )
            
            return True
            
        except Exception as e:
            self.db.db["scraper_queue"].update_one(
                {"type": "race", "id": race_id},
                {"$set": {"status": "error", "error": str(e), "updated_at": datetime.now().isoformat()}}
            )
            
            self.activity_logger.log(
                phase="phase3",
                action="scrape_race",
                target_id=race_id,
                status="error",
                error=str(e)
            )
            
            raise
    
    async def _print_summary(self):
        """Print final summary"""
        print("\n" + "=" * 80)
        print("📊 SCRAPING SUMMARY")
        print("=" * 80)
        
        # Activity log summary
        summary = self.activity_logger.get_summary()
        
        print(f"\nOverall Stats:")
        for status, count in summary.items():
            print(f"  {status}: {count}")
        
        # MongoDB stats
        horse_count = self.db.db["scraper_queue"].count_documents({"type": "horse"})
        race_count = self.db.db["scraper_queue"].count_documents({"type": "race"})
        
        print(f"\nDatabase Stats:")
        print(f"  Horses queued: {horse_count}")
        print(f"  Races queued: {race_count}")
        print(f"  Races collection: {self.db.db['races'].count_documents({})}")
        
        print("\n✅ Scraping completed!")


async def main():
    """Main entry point"""
    # Test with known horses
    test_horse_ids = [
        "HK_2023_J256",  # 祝領
        "HK_2022_H432",  # H432
        "HK_2020_E486",  # 浪漫勇士
    ]
    
    scraper = OverallScraper(max_concurrent=2, headless=True)
    await scraper.run(test_horse_ids)


if __name__ == "__main__":
    asyncio.run(main())
