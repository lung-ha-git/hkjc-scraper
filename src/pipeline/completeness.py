"""
Pipeline: Horse Data Completeness Check + Sync
Part 3 of daily pipeline - ensure horses in recent races have complete data for ML training

Logic:
1. Get all horses that raced in past N days (rolling window)
2. Check completeness of critical fields in horses collection
3. For incomplete horses, queue deep sync
4. Use upsert (delta change) - never overwrite correct data
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Set, Tuple

from src.database.connection import DatabaseConnection
from src.pipeline.deep_sync import sync_single_horse

logger = logging.getLogger(__name__)


# Fields critical for ML training, ordered by priority
CRITICAL_FIELDS = [
    ("current_rating", "rating"),
    ("name", "name"),
    ("jersey_url", "jersey"),
    ("career_starts", "career stats"),
]


def get_recent_horse_ids(days_back: int = 30) -> Set[str]:
    """Get all unique hkjc_horse_ids from racecard_entries in past N days"""
    db = DatabaseConnection()
    if not db.connect():
        return set()
    
    try:
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        entries = list(db.db["racecard_entries"].find(
            {"race_date": {"$gte": start_date}},
            {"hkjc_horse_id": 1}
        ))
        
        ids = {e.get("hkjc_horse_id") for e in entries if e.get("hkjc_horse_id")}
        logger.info(f"Found {len(ids)} unique horses from past {days_back} days")
        return ids
    
    finally:
        db.disconnect()


def check_horse_completeness(hkjc_horse_id: str, db) -> Tuple[bool, list]:
    """
    Check if a horse has complete critical fields in horses collection
    
    Returns:
        (is_complete, list_of_missing_fields)
    """
    horse = db.db["horses"].find_one({"hkjc_horse_id": hkjc_horse_id})
    
    if not horse:
        return False, ["not_in_collection"]
    
    missing = []
    for field, label in CRITICAL_FIELDS:
        value = horse.get(field)
        if value is None or value == "" or value == 0:
            missing.append(label)
    
    return len(missing) == 0, missing


def get_already_synced_recently(db, hours: int = 24) -> Set[str]:
    """Get horse IDs that were recently synced (within N hours)"""
    cutoff = datetime.now() - timedelta(hours=hours)
    
    entries = list(db.db["scrape_queue"].find(
        {
            "type": "horse_detail",
            "modified_at": {"$gte": cutoff},
            "status": {"$in": ["completed", "in_progress"]}
        },
        {"horse_id": 1}
    ))
    
    return {e.get("horse_id") for e in entries if e.get("horse_id")}


def add_to_sync_queue(db, hkjc_horse_id: str) -> bool:
    """Add horse to scrape_queue if not already present"""
    existing = db.db["scrape_queue"].find_one({
        "type": "horse_detail",
        "horse_id": hkjc_horse_id,
        "status": {"$in": ["pending", "in_progress"]}
    })
    
    if existing:
        logger.debug(f"  {hkjc_horse_id} already in queue")
        return False
    
    db.db["scrape_queue"].update_one(
        {
            "type": "horse_detail",
            "horse_id": hkjc_horse_id,
        },
        {
            "$set": {
                "scheduled_scrape_time": datetime.now(),
                "status": "pending",
                "priority": 1,
                "modified_at": datetime.now(),
                "claimed_at": None,
                "claim_count": 0,
            },
            "$setOnInsert": {
                "created_at": datetime.now(),
            }
        },
        upsert=True
    )
    return True


async def completeness_check_and_sync(
    days_back: int = 30,
    dry_run: bool = False,
    skip_sync: bool = False,
) -> dict:
    """
    Part 3: Horse data completeness check + sync
    
    Args:
        days_back: How far back to look for recent races (default 30 days)
        dry_run: If True, only report without syncing
        skip_sync: If True, only check without adding to queue
    
    Returns:
        dict with results summary
    """
    logger.info("=" * 70)
    logger.info("🐴 PART 3: HORSE DATA COMPLETENESS CHECK")
    logger.info("=" * 70)
    
    results = {
        "total_recent_horses": 0,
        "complete": 0,
        "incomplete": 0,
        "queued": 0,
        "skipped_already_synced": 0,
        "missing_by_field": {},
    }
    
    # Step 1: Get horses from recent races
    logger.info(f"\n🔍 Step 1: Finding horses from past {days_back} days...")
    recent_ids = get_recent_horse_ids(days_back)
    results["total_recent_horses"] = len(recent_ids)
    
    if not recent_ids:
        logger.info("   No horses found in recent races")
        return results
    
    # Step 2: Get already synced horses (to avoid re-queueing)
    db = DatabaseConnection()
    if not db.connect():
        logger.error("Cannot connect to MongoDB")
        return results
    
    try:
        already_synced = get_already_synced_recently(db, hours=24)
        logger.info(f"   {len(already_synced)} horses synced in last 24h (will skip)")
        
        # Step 3: Check each horse
        logger.info(f"\n🔍 Step 2: Checking completeness of {len(recent_ids)} horses...")
        
        to_sync = []
        
        for hkjc_horse_id in sorted(recent_ids):
            is_complete, missing = check_horse_completeness(hkjc_horse_id, db)
            
            if is_complete:
                results["complete"] += 1
            else:
                results["incomplete"] += 1
                for m in missing:
                    results["missing_by_field"][m] = results["missing_by_field"].get(m, 0) + 1
                
                if hkjc_horse_id not in already_synced and not skip_sync:
                    to_sync.append(hkjc_horse_id)
        
        # Step 4: Queue incomplete horses for sync
        if dry_run:
            logger.info(f"\n📋 [DRY RUN] Would queue {len(to_sync)} horses for deep sync:")
            for hid in to_sync:
                logger.info(f"   - {hid}")
        elif to_sync:
            logger.info(f"\n🔄 Step 3: Queuing {len(to_sync)} horses for deep sync...")
            
            queued_count = 0
            for hkjc_horse_id in to_sync:
                if add_to_sync_queue(db, hkjc_horse_id):
                    logger.info(f"   ✅ Queued: {hkjc_horse_id}")
                    queued_count += 1
                else:
                    results["skipped_already_synced"] += 1
            
            results["queued"] = queued_count
    
    finally:
        db.disconnect()
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("📊 PART 3 完成")
    logger.info(f"   最近 {days_back} 日賽事馬匹: {results['total_recent_horses']}")
    logger.info(f"   資料完整: {results['complete']}")
    logger.info(f"   資料不完整: {results['incomplete']}")
    logger.info(f"   已加入同步隊列: {results['queued']}")
    logger.info(f"   跳過 (已同步): {results['skipped_already_synced']}")
    if results["missing_by_field"]:
        logger.info(f"   缺失字段:")
        for field, count in sorted(results["missing_by_field"].items()):
            logger.info(f"     - {field}: {count}")
    logger.info("=" * 70)
    
    return results
