"""
Pipeline: Racecards
Scrape upcoming race day racecards
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

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


def _needs_rescrape(db, race_date: str, venue: str, fixture: Dict) -> tuple:
    """
    Check if a race day needs re-scraping.
    
    Returns:
        (needs_scrape: bool, reason: str)
    """
    today = datetime.now()
    race_day = datetime.strptime(race_date, "%Y-%m-%d")
    days_until_race = (race_day - today).days
    
    existing_count = db.db["racecards"].count_documents({
        "race_date": race_date,
        "venue": venue
    })
    expected_count = fixture.get("race_count", 0)
    
    # Always scrape if race day is in 3 days or less (draw/weight updated close to race)
    if days_until_race <= 3:
        return True, f"race day in {days_until_race} day(s) (auto-update window)"
    
    # Skip if race already passed
    if days_until_race < 0:
        return False, "race already passed"
    
    # Check if data is incomplete (e.g., missing draw values)
    entries_with_draw = db.db["racecard_entries"].count_documents({
        "race_date": race_date,
        "venue": venue,
        "draw": {"$ne": None}
    })
    total_entries = db.db["racecard_entries"].count_documents({
        "race_date": race_date,
        "venue": venue
    })
    
    if total_entries > 0 and entries_with_draw == 0:
        return True, "all entries missing draw values"
    
    # Check if already complete
    if existing_count >= expected_count and expected_count > 0:
        return False, f"complete ({existing_count}/{expected_count})"
    
    return True, f"incomplete ({existing_count}/{expected_count})"


async def scrape_next_racecards() -> int:
    """
    Find and scrape upcoming race day racecards.
    Re-scrapes races within 3 days of race day (for draw/weight updates).
    
    Returns:
        Number of races scraped
    """
    db = DatabaseConnection()
    if not db.connect():
        logger.error("Cannot connect to MongoDB")
        return 0
    
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Find ALL upcoming fixtures (not just the first one)
        fixtures = list(db.db["fixtures"].find(
            {"date": {"$gte": today}},
            sort=[("date", 1)]
        ))
        
        if not fixtures:
            logger.warning("No upcoming race day found in fixtures")
            return 0
        
        total_scraped = 0
        
        for fixture in fixtures:
            race_date = fixture["date"]
            venue = fixture.get("venue", "ST")
            scrape_status = fixture.get("scrape_status", "pending")
            
            needs_scrape, reason = _needs_rescrape(db, race_date, venue, fixture)
            
            if not needs_scrape:
                logger.info(f"Skipping {race_date} ({venue}): {reason}")
                continue
            
            logger.info(f"Scraping {race_date} ({venue}): {reason} [status={scrape_status}]")
            
            # Reset status to in_progress
            db.db["fixtures"].update_one(
                {"date": race_date, "venue": venue},
                {"$set": {"scrape_status": "in_progress"}}
            )
            
            # Close DB before scraper uses its own connection
            db.disconnect()
            
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
                # Reconnect and continue to next fixture
                db.connect()
                continue
            
            if count > 0:
                # Mark fixture as completed AND update race_count to actual scraped count
                try:
                    db2 = DatabaseConnection()
                    db2.connect()
                    db2.db["fixtures"].update_one(
                        {"date": race_date, "venue": venue},
                        {"$set": {"scrape_status": "completed", "race_count": count}}
                    )
                    db2.disconnect()
                except Exception:
                    pass
            
            total_scraped += count
            
            # Reconnect for next iteration
            db.connect()
        
        return total_scraped
    
    except Exception as e:
        logger.error(f"Error scraping next racecards: {e}")
        return 0
    finally:
        try:
            db.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test
    count = asyncio.run(scrape_next_racecards())
    print(f"Scraped {count} races")
