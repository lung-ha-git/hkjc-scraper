"""
Pipeline: Racecards
Scrape upcoming race day racecards
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.crawler.racecard_scraper import RaceCardScraper
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


async def scrape_race_day(race_date: str, venue: str = "HV") -> int:
    """
    Scrape all racecards for a specific day
    
    Args:
        race_date: Format YYYY-MM-DD
        venue: HV or ST
    
    Returns:
        Number of races scraped
    """
    async with RaceCardScraper(headless=True, delay=2) as scraper:
        racecards = await scraper.scrape_race_day(race_date, venue)
        
        if not racecards:
            logger.warning(f"No racecards found for {race_date} ({venue})")
            return 0
        
        # Save to MongoDB
        scraper.save_to_mongodb(racecards)
        
        return len(racecards)


async def scrape_next_racecards() -> int:
    """
    Find and scrape next race day racecards
    
    Returns:
        Number of races scraped
    """
    db = DatabaseConnection()
    if not db.connect():
        logger.error("Cannot connect to MongoDB")
        return 0
    
    try:
        # Find next race day from fixtures (use "date" field)
        today = datetime.now().strftime("%Y-%m-%d")
        
        fixture = db.db["fixtures"].find_one(
            {"date": {"$gte": today}},
            sort=[("date", 1)]
        )
        
        if not fixture:
            logger.warning("No upcoming race day found in fixtures")
            return 0
        
        race_date = fixture["date"]
        venue = fixture.get("venue", "ST")
        
        logger.info(f"Found next race day: {race_date} ({venue})")
        
        # Check if already scraped (complete = all races present)
        existing_count = db.db["racecards"].count_documents({
            "race_date": race_date,
            "venue": venue
        })
        expected_count = fixture.get("race_count", 0)
        
        if existing_count >= expected_count and expected_count > 0:
            logger.info(f"Racecards already complete for {race_date} ({venue}): {existing_count}/{expected_count}")
            return 0
        
        # Mark fixture as in_progress
        db.db["fixtures"].update_one(
            {"date": race_date, "venue": venue},
            {"$set": {"scrape_status": "in_progress"}}
        )
        
        # Scrape
        db.disconnect()  # Close before scraper uses its own connection
        count = 0
        try:
            count = await scrape_race_day(race_date, venue)
        except Exception as scrape_err:
            logger.error(f"Scraper error for {race_date} ({venue}): {scrape_err}")
            # Reset to pending so it will retry next run
            try:
                db3 = DatabaseConnection()
                if db3.connect():
                    db3.db["fixtures"].update_one(
                        {"date": race_date, "venue": venue},
                        {"$set": {"scrape_status": "pending"}}
                    )
                    db3.disconnect()
            except Exception:
                pass
            return 0
        
        if count > 0:
            # Mark fixture as completed
            db2 = DatabaseConnection()
            db2.connect()
            db2.db["fixtures"].update_one(
                {"date": race_date, "venue": venue},
                {"$set": {"scrape_status": "completed"}}
            )
            db2.disconnect()
        
        return count
    
    except Exception as e:
        logger.error(f"Error scraping next racecards: {e}")
        return 0
    finally:
        try:
            db.disconnect()
        except Exception:
            pass


def get_latest_scraped_race() -> Optional[Dict]:
    """Get the latest scraped race from MongoDB"""
    db = DatabaseConnection()
    if not db.connect():
        return None
    
    race = db.db["racecards"].find_one(
        sort=[("race_date", -1), ("race_no", -1)]
    )
    
    db.disconnect()
    return race


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test
    count = asyncio.run(scrape_next_racecards())
    print(f"Scraped {count} races")
