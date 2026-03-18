"""
Pipeline: Sync Fixtures
Sync race meeting calendar from HKJC

IMPORTANT: All fixtures use "date" field (not "race_date").
The field "date" is the canonical date string like "2026-03-18".
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict

from src.crawler.fixture_scraper import FixtureScraper
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


async def sync_fixtures(months: List[tuple] = None) -> int:
    """
    Sync race fixtures/calendar to MongoDB
    
    Args:
        months: List of (year, month) tuples to fetch. 
                If None, fetches current + next month
    
    Returns:
        Number of fixtures synced
    """
    if months is None:
        # Default: current month + next 2 months
        now = datetime.now()
        months = []
        for i in range(3):
            d = now + timedelta(days=i*30)
            months.append((str(d.year), f"{d.month:02d}"))
    
    db = DatabaseConnection()
    if not db.connect():
        logger.error("Cannot connect to MongoDB")
        return 0
    
    scraper = FixtureScraper(headless=True)
    total_synced = 0
    
    try:
        for year, month in months:
            logger.info(f"   Fetching {year}-{month}...")
            
            fixtures = await scraper.parse_month(year, month)
            
            for fixture in fixtures:
                race_date = fixture.get("race_date")
                venue = fixture.get("venue")
                
                fixture_doc = {
                    "date": race_date,  # Canonical field: "date"
                    "venue": venue,
                    "race_count": fixture.get("race_count", 8),
                    "first_race_time": fixture.get("first_race_time"),
                    "race_meeting": fixture.get("race_meeting"),
                    "scrape_status": "pending",
                    "updated_at": datetime.now().isoformat(),
                    "racecard_url": fixture.get("racecard_url"),
                    "results_url": fixture.get("results_url"),
                }
                
                # Upsert by date + venue (not race_date)
                db.db["fixtures"].update_one(
                    {"date": race_date, "venue": venue},
                    {"$set": fixture_doc},
                    upsert=True
                )
                total_synced += 1
            
            logger.info(f"   ✅ Synced {len(fixtures)} fixtures for {year}-{month}")
    
    except Exception as e:
        logger.error(f"Error syncing fixtures: {e}")
    
    finally:
        db.disconnect()
    
    return total_synced


def get_next_fixture() -> Dict:
    """Get next upcoming race day from fixtures"""
    db = DatabaseConnection()
    if not db.connect():
        return None
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    fixture = db.db["fixtures"].find_one(
        {"date": {"$gte": today}},
        sort=[("date", 1)]
    )
    
    db.disconnect()
    return fixture


def get_past_fixtures(days_back: int = 30) -> List[Dict]:
    """Get past race days from fixtures (most recent first)"""
    db = DatabaseConnection()
    if not db.connect():
        return []
    
    today = datetime.now()
    start_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    fixtures = list(db.db["fixtures"].find(
        {"date": {"$gte": start_date, "$lt": today.strftime("%Y-%m-%d")}},
        sort=[("date", -1)]
    ))
    
    db.disconnect()
    return fixtures


def get_past_fixture() -> Dict:
    """Get most recent past race day from fixtures"""
    db = DatabaseConnection()
    if not db.connect():
        return None
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    fixture = db.db["fixtures"].find_one(
        {"date": {"$lt": today}},
        sort=[("date", -1)]
    )
    
    db.disconnect()
    return fixture


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test
    count = asyncio.run(sync_fixtures())
    print(f"Synced {count} fixtures")
