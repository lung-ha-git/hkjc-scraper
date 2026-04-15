"""
Backfill ALL pending ST fixtures with racecard data.

Processes all fixtures where:
  - venue is ST
  - scrape_status is "pending" OR racecards are missing

Usage:
    docker exec hkjc-pipeline python3 /app/src/backfill_st_racecards.py
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, "/app")

from src.crawler.racecard_scraper import RaceCardScraper
from src.database.connection import DatabaseConnection


def main():
    db = DatabaseConnection()
    if not db.connect():
        print("❌ Cannot connect to MongoDB")
        return 1

    # Find all pending ST fixtures
    fixtures = list(db.db["fixtures"].find(
        {"venue": "ST", "scrape_status": "pending"},
        sort=[("date", 1)]
    ))
    print(f"Found {len(fixtures)} pending ST fixtures to backfill")
    print()

    if not fixtures:
        print("No pending ST fixtures found")
        db.disconnect()
        return 0

    updated = 0
    errors = 0
    skipped = 0

    async def backfill():
        nonlocal updated, errors, skipped

        async with RaceCardScraper(headless=True, delay=2) as scraper:
            for fix in fixtures:
                race_date = fix["date"]
                venue = fix["venue"]
                expected = fix.get("race_count", 0)

                # Check if already scraped
                existing = db.db["racecards"].count_documents(
                    {"race_date": race_date, "venue": venue}
                )
                if existing >= expected and expected > 0:
                    print(f"⏭️  {race_date} ST: {existing}/{expected} already scraped, marking completed")
                    db.db["fixtures"].update_one(
                        {"date": race_date, "venue": venue},
                        {"$set": {"scrape_status": "completed", "race_count": existing}}
                    )
                    skipped += 1
                    continue

                print(f"🔍 {race_date} ST ({expected} races)...")
                try:
                    racecards = await scraper.scrape_race_day(race_date, venue)
                    count = len(racecards)
                    print(f"   Scraped {count} races")

                    # Upsert each racecard
                    for rc in racecards:
                        if "race_id" not in rc:
                            rc["race_id"] = f"{rc.get('race_date', '').replace('-', '_')}_{rc.get('venue', '')}_{rc.get('race_no', '')}"
                        doc = {
                            **rc,
                            "race_type": scraper._detect_race_type(
                                rc.get("race_name_en", ""),
                                rc.get("race_name_ch", "")
                            ),
                            "scrape_at": datetime.now(),
                        }
                        db.db["racecards"].update_one(
                            {"race_id": rc["race_id"]},
                            {"$set": doc},
                            upsert=True
                        )

                    # Also backfill to races collection
                    for rc in racecards:
                        race_id = rc.get("race_id")
                        race_no = rc.get("race_no")
                        if not race_id:
                            continue
                        doc = {
                            "race_id": race_id,
                            "hkjc_race_id": race_id,
                            "race_date": race_date,
                            "venue": venue,
                            "race_no": race_no,
                            "class": rc.get("class_en") or rc.get("class_ch", ""),
                            "distance": rc.get("distance", 0),
                            "scrape_time": datetime.now().isoformat(),
                        }
                        db.db["races"].update_one(
                            {"race_id": race_id},
                            {"$set": doc},
                            upsert=True
                        )

                    # Mark fixture completed
                    db.db["fixtures"].update_one(
                        {"date": race_date, "venue": venue},
                        {"$set": {"scrape_status": "completed", "race_count": count}}
                    )
                    print(f"   ✅ {count} races saved, fixture marked completed")
                    updated += 1

                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    errors += 1
                    # Reset to pending for retry
                    db.db["fixtures"].update_one(
                        {"date": race_date, "venue": venue},
                        {"$set": {"scrape_status": "pending"}}
                    )

    asyncio.run(backfill())
    db.disconnect()

    print()
    print("=" * 60)
    print(f"  Backfill complete:")
    print(f"  ✅ Updated:  {updated} fixtures")
    print(f"  ⏭️  Skipped:   {skipped} fixtures (already complete)")
    print(f"  ❌ Errors:    {errors} fixtures")
    print("=" * 60)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
