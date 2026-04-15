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

logger = logging.getLogger(__name__)


# Fields critical for ML training, ordered by priority
# Format: (field_name, human_label)
# NOTE: career_starts=0 is valid for new horses, excluded from completeness check
CRITICAL_FIELDS_ML = [
    ("current_rating", "rating"),
]
CRITICAL_FIELDS_DISPLAY = [
    ("name", "name"),
    ("jersey_url", "jersey"),
]


def get_recent_horse_ids(days_back: int = 30) -> Set[str]:
    """Get all unique hkjc_horse_ids from racecard_entries in past N days"""
    db = DatabaseConnection()
    if not db.connect():
        return set()
    
    try:
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        entries = list(db.db["racecard_entries"].find(
            {"date": {"$gte": start_date}},
            {"hkjc_horse_id": 1}
        ))
        
        ids = {e.get("hkjc_horse_id") for e in entries if e.get("hkjc_horse_id")}
        logger.info(f"Found {len(ids)} unique horses from past {days_back} days")
        return ids
    
    finally:
        db.disconnect()


def check_horse_completeness(hkjc_horse_id: str, db) -> Tuple[bool, list, dict]:
    """
    Check if a horse has complete critical fields in horses collection
    
    Returns:
        (is_complete, list_of_missing_ml_fields, missing_display_fields)
        is_complete: True only if ALL ML-critical fields present
    """
    horse = db.db["horses"].find_one({"hkjc_horse_id": hkjc_horse_id})
    
    if not horse:
        return False, ["not_in_collection"], []
    
    missing_ml = []
    missing_display = []
    
    for field, label in CRITICAL_FIELDS_ML:
        value = horse.get(field)
        if value is None or value == "":
            missing_ml.append(label)
    
    for field, label in CRITICAL_FIELDS_DISPLAY:
        value = horse.get(field)
        if value is None or value == "":
            missing_display.append(label)
    
    all_missing = missing_ml + missing_display
    return len(missing_ml) == 0, all_missing, missing_display


def was_horse_recently_synced(db, hkjc_horse_id: str, hours: int = 24) -> bool:
    """
    Check if horse was recently synced by looking at horses.last_updated.
    If last_updated is within N hours, skip re-queuing.
    """
    horse = db.db["horses"].find_one(
        {"hkjc_horse_id": hkjc_horse_id},
        {"last_updated": 1}
    )
    
    if not horse:
        return False
    
    last_updated = horse.get("last_updated")
    if not last_updated:
        return False
    
    # Handle both string and datetime formats
    if isinstance(last_updated, str):
        try:
            last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        except ValueError:
            return False
    
    cutoff = datetime.now() - timedelta(hours=hours)
    return last_updated >= cutoff


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
        "missing_display_only": 0,
    }
    
    # Step 1: Get horses from recent races
    logger.info(f"\n🔍 Step 1: Finding horses from past {days_back} days...")
    recent_ids = get_recent_horse_ids(days_back)
    results["total_recent_horses"] = len(recent_ids)
    
    if not recent_ids:
        logger.info("   No horses found in recent races")
        return results
    
    # Step 2: Check each horse
    db = DatabaseConnection()
    if not db.connect():
        logger.error("Cannot connect to MongoDB")
        return results
    
    try:
        logger.info(f"\n🔍 Step 2: Checking completeness of {len(recent_ids)} horses...")
        
        to_sync = []
        
        for hkjc_horse_id in sorted(recent_ids):
            is_complete, all_missing, missing_display = check_horse_completeness(hkjc_horse_id, db)
            
            if is_complete and not missing_display:
                results["complete"] += 1
            else:
                results["incomplete"] += 1
                
                # ML-critical missing fields
                ml_missing = [m for m in all_missing if m not in missing_display]
                for m in ml_missing:
                    results["missing_by_field"][m] = results["missing_by_field"].get(m, 0) + 1
                
                # Display-only missing (less urgent)
                if missing_display and not ml_missing:
                    results["missing_display_only"] += 1
                
                # Skip if already recently synced
                if was_horse_recently_synced(db, hkjc_horse_id, hours=24):
                    results["skipped_already_synced"] += 1
                elif not skip_sync:
                    # Queue ALL incomplete horses (including those missing display fields like 'name')
                    to_sync.append(hkjc_horse_id)
        
        # Step 3: Queue incomplete horses for sync
        if dry_run:
            if to_sync:
                logger.info(f"\n📋 [DRY RUN] Would queue {len(to_sync)} horses for deep sync:")
                for hid in to_sync:
                    logger.info(f"   - {hid}")
            else:
                logger.info(f"\n📋 [DRY RUN] No horses need syncing")
        elif to_sync:
            logger.info(f"\n🔄 Step 3: Queuing {len(to_sync)} horses for deep sync...")
            
            queued_count = 0
            for hkjc_horse_id in to_sync:
                if add_to_sync_queue(db, hkjc_horse_id):
                    logger.info(f"   ✅ Queued: {hkjc_horse_id}")
                    queued_count += 1
            
            results["queued"] = queued_count
    
    finally:
        db.disconnect()
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("📊 PART 3 完成")
    logger.info(f"   最近 {days_back} 日賽事馬匹: {results['total_recent_horses']}")
    logger.info(f"   資料完整: {results['complete']}")
    logger.info(f"   資料不完整 (ML): {results['incomplete'] - results['missing_display_only']}")
    logger.info(f"   資料不完整 (僅Display): {results['missing_display_only']}")
    logger.info(f"   已加入同步隊列: {results['queued']}")
    logger.info(f"   跳過 (24h內已同步): {results['skipped_already_synced']}")
    if results["missing_by_field"]:
        logger.info(f"   缺失 ML 字段:")
        for field, count in sorted(results["missing_by_field"].items()):
            logger.info(f"     - {field}: {count}")
    logger.info("=" * 70)
    
    return results
