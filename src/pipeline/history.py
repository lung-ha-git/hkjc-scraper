"""
Pipeline: Race History Sync
Sync past race results with gap analysis
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from src.crawler.race_results_scraper import RaceResultsScraper
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


async def sync_race_result(race_date: str, venue: str, race_no: int) -> bool:
    """
    Sync a single race result
    
    Args:
        race_date: YYYY-MM-DD
        venue: HV or ST
        race_no: Race number
    
    Returns:
        True if successful
    """
    async with RaceResultsScraper(headless=True) as scraper:
        try:
            result = await scraper.scrape_race_result(race_date, venue, race_no)
            
            if not result:
                return False
            
            # Upsert race result
            race_id = f"{race_date.replace('-', '_')}_{venue}_{race_no}"
            
            race_doc = {
                "race_id": race_id,
                "race_date": race_date,
                "venue": venue,
                "race_no": race_no,
                "results": result.get("results"),
                "payout": result.get("payout"),
                "scrape_time": datetime.now().isoformat()
            }
            
            db = DatabaseConnection()
            if not db.connect():
                return False
            
            db.db["races"].update_one(
                {"race_id": race_id},
                {"$set": race_doc},
                upsert=True
            )
            
            db.disconnect()
            return True
        
        except Exception as e:
            logger.error(f"Error syncing race {race_date} {venue} {race_no}: {e}")
            return False


async def sync_past_race_results(days_back: int = 7) -> int:
    """
    Sync past race results with gap analysis
    
    Args:
        days_back: How many days back to check
    
    Returns:
        Number of races synced
    """
    db = DatabaseConnection()
    if not db.connect():
        logger.error("Cannot connect to MongoDB")
        return 0
    
    try:
        # Get past race days from fixtures
        today = datetime.now()
        start_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        fixtures = list(db.db["fixtures"].find({
            "race_date": {"$gte": start_date, "$lt": today.strftime("%Y-%m-%d")},
            "venue": {"$in": ["HV", "ST"]}
        }))
        
        if not fixtures:
            logger.info("No recent fixtures found")
            return 0
        
        synced = 0
        
        for fixture in fixtures:
            race_date = fixture["race_date"]
            venue = fixture["venue"]
            expected_races = fixture.get("race_count", 8)
            
            logger.info(f"Checking {race_date} ({venue}) - {expected_races} races")
            
            # Gap analysis: check which races are missing
            for race_no in range(1, expected_races + 1):
                race_id = f"{race_date.replace('-', '_')}_{venue}_{race_no}"
                
                # Check if race result exists
                exists = db.db["races"].find_one({"race_id": race_id})
                
                if not exists:
                    # Missing - try to scrape
                    logger.info(f"   Missing race {race_no}, attempting scrape...")
                    
                    db.disconnect()
                    
                    success = await sync_race_result(race_date, venue, race_no)
                    
                    if success:
                        synced += 1
                    
                    await asyncio.sleep(2)  # Rate limiting
                    
                    db.connect()
        
        return synced
    
    except Exception as e:
        logger.error(f"Error in sync_past_race_results: {e}")
        return 0
    finally:
        db.disconnect()


def get_race_gaps(days: int = 30) -> List[Dict]:
    """Analyze gaps in race history"""
    db = DatabaseConnection()
    if not db.connect():
        return []
    
    today = datetime.now()
    start_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Get all fixtures in range
    fixtures = list(db.db["fixtures"].find({
        "race_date": {"$gte": start_date}
    }))
    
    gaps = []
    
    for fixture in fixtures:
        race_date = fixture["race_date"]
        venue = fixture["venue"]
        expected = fixture.get("race_count", 8)
        
        # Count actual results
        actual = db.db["races"].count_documents({
            "race_date": race_date,
            "venue": venue
        })
        
        if actual < expected:
            gaps.append({
                "race_date": race_date,
                "venue": venue,
                "expected": expected,
                "actual": actual,
                "missing": expected - actual
            })
    
    db.disconnect()
    return gaps


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test
    count = asyncio.run(sync_past_race_results(days_back=7))
    print(f"Synced {count} race results")
