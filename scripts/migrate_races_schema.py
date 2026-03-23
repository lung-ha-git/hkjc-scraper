#!/usr/bin/env python3
"""
Migration: races collection — normalize payout keys + field names

- payout keys: 獨贏→win, 位置→place, 連贏→quinella, etc.
- Field: "payouts" (Chinese) → "payout" (English)
- Field: "result" (array) → "results" (array)
- Deduplicate: rename duplicate docs if any

Run: python3 scripts/migrate_races_schema.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv('.env.dev')

from src.database.connection import get_db
from src.constants.payout_map import POOL_NAME_MAP, normalize_payout_keys

def migrate_races():
    db = get_db()
    races = db.get_collection('races')

    # 1. Find docs with payouts (Chinese keys, old field name)
    old_docs = list(races.find({
        "$or": [
            {"payouts": {"$exists": True}},
            {"result": {"$exists": True}},
        ]
    }))

    print(f"Found {len(old_docs)} docs needing migration")

    renamed = 0
    for doc in old_docs:
        set_ops = {}
        unset_ops = {}

        # Normalize payout keys: payouts (Chinese) → payout (English)
        if "payouts" in doc:
            payouts = doc["payouts"]
            # Only migrate if there are Chinese keys to normalize
            has_chinese = isinstance(payouts, dict) and any(k in POOL_NAME_MAP for k in payouts.keys())
            if isinstance(payouts, dict) and any(k in POOL_NAME_MAP for k in payouts.keys()):
                set_ops["payout"] = normalize_payout_keys(payouts)
            elif isinstance(payouts, dict):
                set_ops["payout"] = payouts
            else:
                set_ops["payout"] = payouts
            unset_ops["payouts"] = ""

        # Rename result → results
        if "result" in doc:
            set_ops["results"] = doc["result"]
            unset_ops["result"] = ""

        if set_ops or unset_ops:
            if set_ops:
                races.update_one({"_id": doc["_id"]}, {"$set": set_ops})
            if unset_ops:
                races.update_one({"_id": doc["_id"]}, {"$unset": unset_ops})
            renamed += 1
            race_id = doc.get("race_id", "?")
            print(f"  ✅ {race_id}")

    print(f"\n✅ Migrated {renamed} documents")

    # 2. Verify: count docs with old fields
    remaining_old = races.count_documents({
        "$or": [
            {"payouts": {"$exists": True}},
            {"result": {"$exists": True}},
        ]
    })
    print(f"   Remaining old docs: {remaining_old}")

    # 3. Sample check
    doc = races.find_one({"race_id": "2026_03_22_ST_10"})
    if doc:
        print(f"\n   Sample (2026_03_22_ST_10):")
        print(f"   - payout keys: {list(doc.get('payout', {}).keys())[:5]}")
        print(f"   - results count: {len(doc.get('results', []))}")
        print(f"   - payouts present: {'payouts' in doc}")

    # 4. Update race_payouts collection keys too
    race_payouts = db.get_collection('race_payouts')
    old_payouts = list(race_payouts.find({"pools": {"$exists": True}}))
    fixed = 0
    for doc in old_payouts:
        pools = doc.get("pools", {})
        if isinstance(pools, dict) and any(k in POOL_NAME_MAP for k in pools.keys()):
            normalized = normalize_payout_keys(pools)
            race_payouts.update_one(
                {"_id": doc["_id"]},
                {"$set": {"pools": normalized}}
            )
            fixed += 1
    print(f"\n   race_payouts collections migrated: {fixed}")

if __name__ == "__main__":
    migrate_races()
