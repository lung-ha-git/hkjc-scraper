"""
Backfill ALL historical race results into races collection.

Two purposes:
  1. ST: Scrape ST historical results (race_results_scraper -> races collection)
  2. HV: Enrich existing partial HV records with full metadata (class, distance, etc.)

Uses racecards to determine which races to scrape.

Usage:
    docker exec hkjc-pipeline python3 /app/src/backfill_st_results.py
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, "/app")

from src.crawler.race_results_scraper import RaceResultsScraper
from src.database.connection import DatabaseConnection


def main():
    db = DatabaseConnection()
    if not db.connect():
        print("❌ Cannot connect to MongoDB")
        return 1

    # Get all dates + venues from racecards
    st_dates = db.db["racecards"].distinct("race_date", {"venue": "ST"})
    hv_dates = db.db["racecards"].distinct("race_date", {"venue": "HV"})
    st_dates.sort()
    hv_dates.sort()
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"ST dates to backfill: {len(st_dates)}")
    print(f"HV dates to enrich:    {len(hv_dates)}")
    print()

    updated = 0
    errors = 0

    async def run_scraping():
        nonlocal updated, errors

        async with RaceResultsScraper(headless=True) as scraper:
            # ── HV: Enrich existing partial records ────────────────────────
            for race_date in hv_dates:
                if race_date > today:
                    print(f"⏭️  HV {race_date}: future, skip")
                    continue

                race_nos = db.db["racecards"].distinct("race_no", {
                    "race_date": race_date, "venue": "HV"
                })
                race_nos.sort()
                print(f"\n🔍 HV {race_date}: {len(race_nos)} races")

                for race_no in race_nos:
                    race_id = f"{race_date.replace('-', '_')}_HV_{race_no}"

                    # Check if already enriched
                    existing = db.db["races"].find_one({"race_id": race_id})
                    if existing and existing.get("class"):
                        print(f"   ⏭️  R{race_no}: already enriched")
                        continue

                    print(f"   🔍 R{race_no}...", end=" ", flush=True)
                    try:
                        parts = race_date.split("-")
                        date_hkjc = f"{parts[0]}/{parts[1]}/{parts[2]}"
                        result = await scraper.scrape_race(date_hkjc, "HV", race_no)
                        if result:
                            meta = result.get("metadata", {})
                            # Upsert race doc (partial HV records)
                            doc = {
                                "hkjc_race_id": race_id,
                                "race_id": race_id,
                                "race_date": race_date,
                                "venue": "HV",
                                "race_no": race_no,
                                "class": meta.get("race_class", ""),
                                "distance": meta.get("distance", 0),
                                "track_condition": meta.get("track", ""),
                                "prize": meta.get("prize", ""),
                                "modified_at": datetime.now().isoformat(),
                            }
                            db.db["races"].update_one(
                                {"race_id": race_id},
                                {"$set": doc}
                            )
                            print(f"✅ {meta.get('distance', '?')}m {meta.get('race_class', '?')}")
                            updated += 1
                        else:
                            print("❌ None")
                    except Exception as e:
                        print(f"❌ {e}")
                        errors += 1
                    await asyncio.sleep(0.5)

            # ── ST: Full backfill ─────────────────────────────────────
            for race_date in st_dates:
                if race_date > today:
                    print(f"⏭️  ST {race_date}: future, skip")
                    continue

                race_nos = db.db["racecards"].distinct("race_no", {
                    "race_date": race_date, "venue": "ST"
                })
                race_nos.sort()
                print(f"\n🔍 ST {race_date}: {len(race_nos)} races")

                for race_no in race_nos:
                    race_id = f"{race_date.replace('-', '_')}_ST_{race_no}"

                    # Check if already scraped
                    existing = db.db["races"].find_one({"race_id": race_id})
                    if existing and existing.get("results"):
                        print(f"   ⏭️  R{race_no}: already has results")
                        continue

                    print(f"   🔍 R{race_no}...", end=" ", flush=True)
                    try:
                        parts = race_date.split("-")
                        date_hkjc = f"{parts[0]}/{parts[1]}/{parts[2]}"
                        result = await scraper.scrape_race(date_hkjc, "ST", race_no)
                        if result:
                            await scraper.save_to_mongodb(result)
                            meta = result.get("metadata", {})
                            print(f"✅ {meta.get('distance', '?')}m | {len(result.get('results', []))} horses")
                            updated += 1
                        else:
                            print("❌ None")
                    except Exception as e:
                        print(f"❌ {e}")
                        errors += 1
                    await asyncio.sleep(0.5)

    asyncio.run(run_scraping())
    db.disconnect()

    print()
    print("=" * 60)
    print(f"  ✅ Scraped/enriched: {updated} races")
    print(f"  ❌ Errors:           {errors} races")
    print("=" * 60)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
