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
        # Get past race days from races collection (not fixtures!)
        today = datetime.now()
        start_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        # Query races collection for past races
        past_races = list(db.db["races"].find({
            "race_date": {"$gte": start_date, "$lt": today.strftime("%Y-%m-%d")}
        }).sort("race_date", 1))
        
        if not past_races:
            logger.info("No past races found in races collection")
            return 0
        
        # Group by race_date and venue
        race_days = {}
        for race in past_races:
            key = f"{race['race_date']}_{race['venue']}"
            if key not in race_days:
                race_days[key] = {
                    "race_date": race["race_date"],
                    "venue": race["venue"],
                    "races": []
                }
            race_days[key]["races"].append(race)
        
        synced = 0
        
        for key, data in race_days.items():
            race_date = data["race_date"]
            venue = data["venue"]
            races = data["races"]
            
            logger.info(f"Checking {race_date} ({venue}) - {len(races)} races")
            
            for race in races:
                race_id = race.get("race_id")
                race_no = race.get("race_no")
                
                # Check if race has complete results
                if not race.get("results") or not race.get("payout"):
                    logger.info(f"   Incomplete race {race_no} ({race_id}), attempting re-scrape...")
                    
                    db.disconnect()
                    
                    success = await sync_race_result(race_date, venue, race_no)
                    
                    if success:
                        synced += 1
                    
                    await asyncio.sleep(2)  # Rate limiting
                    db.connect()
                    
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
        "date": {"$gte": start_date}
    }))
    
    gaps = []
    
    for fixture in fixtures:
        race_date = fixture["date"]  # Canonical field: "date"
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
