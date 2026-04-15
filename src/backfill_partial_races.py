"""
Backfill missing race metadata for partial records in races collection.

These 27 partial records (Mar 18, Mar 25, Apr 8 HV) have results/payout
but are missing: hkjc_race_id, class, distance, track_condition, prize.

Uses racecard_scraper (GraphQL) which returns class_en, class_ch, distance.
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, "/app")

from src.crawler.racecard_scraper import RaceCardScraper
from src.database.connection import DatabaseConnection


DATES_VENUES = [
    ("2026-03-18", "HV"),
    ("2026-03-25", "HV"),
    ("2026-04-08", "HV"),
]


def main():
    db = DatabaseConnection()
    if not db.connect():
        print("❌ Cannot connect to MongoDB")
        return 1

    updated = 0
    errors = 0

    async def backfill():
        nonlocal updated, errors
        async with RaceCardScraper(headless=True, delay=2) as scraper:
            for race_date, venue in DATES_VENUES:
                print(f"\n🔍 Backfilling {race_date} ({venue})...")
                try:
                    racecards = await scraper.scrape_race_day(race_date, venue)
                    print(f"   Got {len(racecards)} races from scraper")

                    for rc in racecards:
                        race_no = rc.get("race_no")
                        if not race_no:
                            continue
                        race_id = f"{race_date.replace('-', '_')}_{venue}_{race_no}"

                        # Build complete doc
                        doc = {
                            "hkjc_race_id": race_id,
                            "race_id": race_id,
                            "race_date": race_date,
                            "venue": venue,
                            "race_no": race_no,
                            "class": rc.get("class_en") or rc.get("class_ch", ""),
                            "class_en": rc.get("class_en", ""),
                            "class_ch": rc.get("class_ch", ""),
                            "distance": rc.get("distance", 0),
                            "track_condition": rc.get("race_track", ""),
                            "prize": rc.get("prize", ""),
                            "modified_at": datetime.now().isoformat(),
                        }

                        result = db.db["races"].update_one(
                            {"race_id": race_id},
                            {"$set": doc}
                        )
                        if result.modified_count > 0 or result.matched_count > 0:
                            print(f"   ✅ R{race_no}: {doc['class']} {doc['distance']}m")
                            updated += 1
                        else:
                            print(f"   ⚠️  R{race_no}: no match in races collection")

                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    errors += 1

    asyncio.run(backfill())
    db.disconnect()

    print(f"\n{'='*60}")
    print(f"  Backfill complete: {updated} updated, {errors} errors")
    print(f"{'='*60}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
