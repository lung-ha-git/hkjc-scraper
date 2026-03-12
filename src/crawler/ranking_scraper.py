"""
HKJC Jockey and Trainer Ranking Scraper
Fetch ranking data from:
- Jockey: https://racing.hkjc.com/zh-hk/local/info/jockey-ranking
- Trainer: https://racing.hkjc.com/zh-hk/local/info/trainer-ranking
"""

import asyncio
import re
from playwright.async_api import async_playwright
from typing import List, Dict, Optional
from datetime import datetime
import sys
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class RankingScraper:
    """Scrape jockey and trainer ranking data from HKJC"""
    
    JOCKEY_URL = "https://racing.hkjc.com/zh-hk/local/info/jockey-ranking?season=Current&view=Numbers&racecourse=ALL"
    TRAINER_URL = "https://racing.hkjc.com/zh-hk/local/info/trainer-ranking?season=Current&view=Numbers&racecourse=ALL"
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.playwright = None
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    def parse_prize_money(self, prize_str: str) -> int:
        """Convert prize money string to integer"""
        if not prize_str:
            return 0
        # Remove $ and commas
        cleaned = prize_str.replace("$", "").replace(",", "").strip()
        try:
            return int(cleaned)
        except ValueError:
            return 0
    
    async def scrape_jockeys(self) -> List[Dict]:
        """Scrape jockey ranking data"""
        logger.info("🏇 Scraping jockey rankings...")
        
        page = await self.browser.new_page()
        await page.goto(self.JOCKEY_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        
        table = await page.query_selector("table.table_bd")
        if not table:
            logger.error("No table found for jockeys")
            await page.close()
            return []
        
        rows = await table.query_selector_all("tr")
        
        jockeys = []
        current_season = None
        
        for row in rows[2:]:  # Skip header rows
            cells = await row.query_selector_all("td")
            if len(cells) < 7:
                continue
            
            cell_texts = [await cell.inner_text() for cell in cells]
            name = cell_texts[0].strip()
            
            # Skip section headers like "在港退役騎師"
            if name in ["在港退役騎師", "在港現役騎師"]:
                continue
            
            # Skip if name is empty
            if not name:
                continue
            
            try:
                jockey = {
                    "name": name,
                    "wins": int(cell_texts[1].strip()) if cell_texts[1].strip().isdigit() else 0,
                    "seconds": int(cell_texts[2].strip()) if cell_texts[2].strip().isdigit() else 0,
                    "thirds": int(cell_texts[3].strip()) if cell_texts[3].strip().isdigit() else 0,
                    "fourths": int(cell_texts[4].strip()) if cell_texts[4].strip().isdigit() else 0,
                    "fifths": int(cell_texts[5].strip()) if cell_texts[5].strip().isdigit() else 0,
                    "total_rides": int(cell_texts[6].strip()) if cell_texts[6].strip().isdigit() else 0,
                    "prize_money": cell_texts[7].strip() if len(cell_texts) > 7 else "",
                    "prize_money_int": self.parse_prize_money(cell_texts[7].strip()) if len(cell_texts) > 7 else 0,
                    "season": "2025/2026",  # Current season
                    "scrape_date": datetime.now().isoformat()
                }
                jockeys.append(jockey)
            except (ValueError, IndexError) as e:
                logger.warning(f"Error parsing jockey row: {name}, {e}")
                continue
        
        await page.close()
        logger.info(f"   ✅ Found {len(jockeys)} jockeys")
        return jockeys
    
    async def scrape_trainers(self) -> List[Dict]:
        """Scrape trainer ranking data"""
        logger.info("🏇 Scraping trainer rankings...")
        
        page = await self.browser.new_page()
        await page.goto(self.TRAINER_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        
        table = await page.query_selector("table.table_bd")
        if not table:
            logger.error("No table found for trainers")
            await page.close()
            return []
        
        rows = await table.query_selector_all("tr")
        
        trainers = []
        
        for row in rows[2:]:  # Skip header rows
            cells = await row.query_selector_all("td")
            if len(cells) < 7:
                continue
            
            cell_texts = [await cell.inner_text() for cell in cells]
            name = cell_texts[0].strip()
            
            # Skip section headers
            if name in ["在港退役練馬師", "在港現役練馬師"]:
                continue
            
            if not name:
                continue
            
            try:
                trainer = {
                    "name": name,
                    "wins": int(cell_texts[1].strip()) if cell_texts[1].strip().isdigit() else 0,
                    "seconds": int(cell_texts[2].strip()) if cell_texts[2].strip().isdigit() else 0,
                    "thirds": int(cell_texts[3].strip()) if cell_texts[3].strip().isdigit() else 0,
                    "fourths": int(cell_texts[4].strip()) if cell_texts[4].strip().isdigit() else 0,
                    "fifths": int(cell_texts[5].strip()) if cell_texts[5].strip().isdigit() else 0,
                    "total_horses": int(cell_texts[6].strip()) if cell_texts[6].strip().isdigit() else 0,
                    "prize_money": cell_texts[7].strip() if len(cell_texts) > 7 else "",
                    "prize_money_int": self.parse_prize_money(cell_texts[7].strip()) if len(cell_texts) > 7 else 0,
                    "season": "2025/2026",
                    "scrape_date": datetime.now().isoformat()
                }
                trainers.append(trainer)
            except (ValueError, IndexError) as e:
                logger.warning(f"Error parsing trainer row: {name}, {e}")
                continue
        
        await page.close()
        logger.info(f"   ✅ Found {len(trainers)} trainers")
        return trainers
    
    async def scrape_all(self) -> tuple[List[Dict], List[Dict]]:
        """Scrape both jockeys and trainers"""
        jockeys = await self.scrape_jockeys()
        trainers = await self.scrape_trainers()
        return jockeys, trainers
    
    def save_to_mongodb(self, jockeys: List[Dict], trainers: List[Dict]) -> bool:
        """Save data to MongoDB"""
        logger.info("💾 Saving to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            logger.error("Cannot connect to MongoDB")
            return False
        
        now = datetime.now().isoformat()
        
        # Update jockeys
        if jockeys:
            # Get existing jockey IDs from old collection
            existing = {doc["jockey_id"]: doc["name"] 
                       for doc in db.jockeys.find({}, {"jockey_id": 1, "name": 1})}
            
            # Match by name to get jockey_id
            for jockey in jockeys:
                jockey_id = self._find_jockey_id(jockey["name"], existing)
                jockey["jockey_id"] = jockey_id
                jockey["created_at"] = now
                jockey["modified_at"] = now
            
            # Upsert each jockey
            for jockey in jockeys:
                db.jockeys.update_one(
                    {"jockey_id": jockey["jockey_id"]},
                    {"$set": jockey},
                    upsert=True
                )
            logger.info(f"   ✅ Updated {len(jockeys)} jockeys")
        
        # Update trainers
        if trainers:
            existing = {doc["trainer_id"]: doc["name"] 
                       for doc in db.trainers.find({}, {"trainer_id": 1, "name": 1})}
            
            for trainer in trainers:
                trainer_id = self._find_trainer_id(trainer["name"], existing)
                trainer["trainer_id"] = trainer_id
                trainer["created_at"] = now
                trainer["modified_at"] = now
            
            for trainer in trainers:
                db.trainers.update_one(
                    {"trainer_id": trainer["trainer_id"]},
                    {"$set": trainer},
                    upsert=True
                )
            logger.info(f"   ✅ Updated {len(trainers)} trainers")
        
        db.disconnect()
        return True
    
    def _find_jockey_id(self, name: str, existing: dict) -> str:
        """Find jockey_id by name from existing data"""
        for jockey_id, jockey_name in existing.items():
            if jockey_name == name:
                return jockey_id
        # If not found, use a slugified version
        return name[:3].upper()
    
    def _find_trainer_id(self, name: str, existing: dict) -> str:
        """Find trainer_id by name from existing data"""
        for trainer_id, trainer_name in existing.items():
            if trainer_name == name:
                return trainer_id
        return name[:3].upper()


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape HKJC jockey and trainer rankings")
    parser.add_argument("--jockeys-only", action="store_true", help="Scrape jockeys only")
    parser.add_argument("--trainers-only", action="store_true", help="Scrape trainers only")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    async with RankingScraper(headless=args.headless) as scraper:
        if args.jockeys_only:
            jockeys = await scraper.scrape_jockeys()
            trainers = []
        elif args.trainers_only:
            jockeys = []
            trainers = await scraper.scrape_trainers()
        else:
            jockeys, trainers = await scraper.scrape_all()
        
        # Save to MongoDB
        scraper.save_to_mongodb(jockeys, trainers)
        
        print("\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"Jockeys: {len(jockeys)}")
        print(f"Trainers: {len(trainers)}")


if __name__ == "__main__":
    asyncio.run(main())
