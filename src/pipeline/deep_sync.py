"""
Pipeline: Deep Horse Data Sync
Sync horse-related data (stats, medical, movements, ratings, workouts)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Set

from src.crawler.complete_horse_scraper import CompleteHorseScraper
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


async def sync_single_horse(horse_id: str, force: bool = False) -> bool:
    """
    Sync all data for a single horse
    
    Args:
        horse_id: HKJC horse ID
        force: Force re-scrape even if exists
    
    Returns:
        True if successful
    """
    scraper = CompleteHorseScraper(headless=True, delay=2)
    try:
        result = await scraper.scrape_horse_complete(horse_id)
        
        if not result:
            logger.warning(f"No data returned for {horse_id}")
            return False
        
        db = DatabaseConnection()
        if not db.connect():
            return False
        
        now = datetime.now().isoformat()
        
        # Upsert basic horse info
        basic = result.get("basic_info", {})
        if basic:
            horse_doc = {
                "hkjc_horse_id": horse_id,
                "name": basic.get("name"),
                "name_zh": basic.get("name_zh"),
                "import_type": basic.get("import_type"),
                "sex": basic.get("sex"),
                "colour": basic.get("colour"),
                "sire": basic.get("sire"),
                "dam": basic.get("dam"),
                "owner": basic.get("owner"),
                "current_rating": basic.get("current_rating"),
                "updated_at": now
            }
            
            db.db["horses"].update_one(
                {"hkjc_horse_id": horse_id},
                {"$set": horse_doc},
                upsert=True
            )
        
        # Upsert race history
        race_history = result.get("race_history", [])
        for race in race_history:
            race["hkjc_horse_id"] = horse_id
            race["scrape_at"] = now
        
        if race_history:
            for race in race_history:
                db.db["horse_race_history"].update_one(
                    {"hkjc_horse_id": horse_id, "race_date": race.get("race_date"), "race_id": race.get("race_id")},
                    {"$set": race},
                    upsert=True
                )
        
        # Upsert distance stats
        distance_stats = result.get("distance_stats", [])
        for stat in distance_stats:
            stat["hkjc_horse_id"] = horse_id
            stat["scrape_at"] = now
        
        if distance_stats:
            for stat in distance_stats:
                db.db["horse_distance_stats"].update_one(
                    {"hkjc_horse_id": horse_id, "distance": stat.get("distance"), "course": stat.get("course")},
                    {"$set": stat},
                    upsert=True
                )
        
        # Upsert workouts
        workouts = result.get("workouts", [])
        for wo in workouts:
            wo["hkjc_horse_id"] = horse_id
            wo["scrape_at"] = now
        
        if workouts:
            for wo in workouts:
                db.db["horse_workouts"].update_one(
                    {"hkjc_horse_id": horse_id, "workout_date": wo.get("workout_date"), "track": wo.get("track")},
                    {"$set": wo},
                    upsert=True
                )
        
        # Upsert medical records
        medical = result.get("medical", [])
        for m in medical:
            m["hkjc_horse_id"] = horse_id
            m["scrape_at"] = now
        
        if medical:
            for m in medical:
                db.db["horse_medical"].update_one(
                    {"hkjc_horse_id": horse_id, "date": m.get("date"), "type": m.get("type")},
                    {"$set": m},
                    upsert=True
                )
        
        # Upsert movements
        movements = result.get("movements", [])
        for mv in movements:
            mv["hkjc_horse_id"] = horse_id
            mv["scrape_at"] = now
        
        if movements:
            for mv in movements:
                db.db["horse_movements"].update_one(
                    {"hkjc_horse_id": horse_id, "date": mv.get("date"), "from_stable": mv.get("from_stable")},
                    {"$set": mv},
                    upsert=True
                )
        
        # Upsert ratings
        ratings = result.get("ratings", [])
        for r in ratings:
            r["hkjc_horse_id"] = horse_id
            r["scrape_at"] = now
        
        if ratings:
            for r in ratings:
                db.db["horse_ratings"].update_one(
                    {"hkjc_horse_id": horse_id, "rating_date": r.get("rating_date")},
                    {"$set": r},
                    upsert=True
                )
        
        db.disconnect()
        return True

    except Exception as e:
        logger.error(f"Error syncing horse {horse_id}: {e}")
        return False


async def deep_sync_horse_data(days_back: int = 7, limit: int = 50) -> int:
    """
    Deep sync horse data for horses in recent races
    
    Args:
        days_back: Check races from last N days
        limit: Max horses to sync per run
    
    Returns:
        Number of horses synced
    """
    db = DatabaseConnection()
    if not db.connect():
        logger.error("Cannot connect to MongoDB")
        return 0
    
    try:
        # Find horses that need updating
        # Get horses from recent races
        today = datetime.now()
        start_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        # Get distinct horse IDs from recent race entries
        pipeline = [
            {"$match": {"race_date": {"$gte": start_date}}},
            {"$group": {"_id": "$horse_id"}}
        ]
        
        recent_horse_ids = [doc["_id"] for doc in db.db["racecard_entries"].aggregate(pipeline)]
        
        if not recent_horse_ids:
            logger.info("No recent horses found")
            return 0
        
        # Filter to horses that haven't been updated recently
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        
        horses_to_sync = []
        for horse_id in recent_horse_ids:
            if not horse_id:
                continue
            
            horse = db.db["horses"].find_one({"hkjc_horse_id": horse_id})
            
            if not horse or horse.get("updated_at", "") < cutoff:
                horses_to_sync.append(horse_id)
        
        if not horses_to_sync:
            logger.info("All horses are up to date")
            return 0
        
        # Limit
        horses_to_sync = horses_to_sync[:limit]
        
        logger.info(f"Syncing {len(horses_to_sync)} horses...")
        
        synced = 0
        for horse_id in horses_to_sync:
            success = await sync_single_horse(horse_id)
            
            if success:
                synced += 1
            
            await asyncio.sleep(1)  # Rate limiting
        
        return synced
    
    except Exception as e:
        logger.error(f"Error in deep_sync: {e}")
        return 0
    finally:
        db.disconnect()


def get_horses_needing_sync(days: int = 30) -> List[Dict]:
    """Get list of horses that need syncing"""
    db = DatabaseConnection()
    if not db.connect():
        return []
    
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    # Horses not updated in last N days
    horses = list(db.db["horses"].find(
        {"updated_at": {"$lt": cutoff}},
        {"hkjc_horse_id": 1, "name": 1, "updated_at": 1}
    ).limit(100))
    
    db.disconnect()
    return horses


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test
    count = asyncio.run(deep_sync_horse_data(days_back=7, limit=10))
    print(f"Synced {count} horses")
