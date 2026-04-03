"""
Sync racecard_entries with horses collection
Fill hkjc_horse_id field in racecard_entries by matching horse_id suffix to horses.hkjc_horse_id

Usage:
    python3 scripts/sync_racecard_entry_horse_ids.py [--dry-run]
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + '/..')

from pymongo import MongoClient
from datetime import datetime
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def build_suffix_map(db):
    """Build partial_id -> hkjc_horse_id mapping from horses collection"""
    suffix_map = {}
    for h in db.horses.find({}, {'hkjc_horse_id': 1}):
        fid = h.get('hkjc_horse_id', '')
        parts = fid.split('_')
        if len(parts) == 3:
            suffix = parts[2]  # e.g., 'K290'
            suffix_map[suffix] = fid  # e.g., 'HK_2024_K290'
    logger.info(f"Built suffix map: {len(suffix_map)} horses")
    return suffix_map


def sync_racecard_entries(dry_run: bool = True):
    db = MongoClient('mongodb://localhost:27017/')['hkjc_racing_dev']
    
    suffix_map = build_suffix_map(db)
    
    # Find all racecard_entries that need syncing
    entries = list(db.racecard_entries.find({}))
    logger.info(f"Processing {len(entries)} racecard_entries...")
    
    updated = 0
    already_set = 0
    not_found = 0
    
    for entry in entries:
        race_id = entry.get('race_id')
        partial_id = entry.get('horse_id')
        current_hkjc = entry.get('hkjc_horse_id')
        
        if not partial_id:
            not_found += 1
            continue
        
        if partial_id not in suffix_map:
            logger.warning(f"  No match for horse_id '{partial_id}' ({entry.get('horse_name')})")
            not_found += 1
            continue
        
        full_id = suffix_map[partial_id]
        
        if current_hkjc == full_id:
            already_set += 1
            continue
        
        if dry_run:
            logger.info(f"  [DRY RUN] Would set hkjc_horse_id: {race_id} {partial_id} -> {full_id}")
        else:
            db.racecard_entries.update_one(
                {'_id': entry['_id']},
                {'$set': {'hkjc_horse_id': full_id}}
            )
            updated += 1
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Summary: updated={updated}, already_set={already_set}, not_found={not_found}")
    logger.info(f"Total: {len(entries)} racecard_entries")
    if dry_run:
        logger.info("[DRY RUN] Run with --no-dry-run to actually update")
    
    return updated, already_set, not_found


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-dry-run', dest='dry_run', action='store_false')
    parser.add_argument('--dry-run', dest='dry_run', action='store_true', default=True)
    args = parser.parse_args()
    
    sync_racecard_entries(dry_run=args.dry_run)
