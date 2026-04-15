"""
Full historical ST race results backfill using fixtures as source.

Covers ALL past ST races from 2023-09 to 2026-04.
HKJC results pages go back years — we can scrape everything.

Usage:
    docker exec hkjc-pipeline python3 /app/src/backfill_st_historical.py
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

    today = datetime.now().strftime("%Y-%m-%d")

    # Get ALL past ST fixtures
    st_fixtures = list(db.db["fixtures"].find(
        {"venue": "ST", "date": {"$lte": today}}
    ).sort("date", 1))

    past_dates = [(f["date"], f.get("race_count", 8)) for f in st_fixtures]
    print(f"ST historical fixtures to backfill: {len(past_dates)}")
    print(f"Date range: {past_dates[0][0]} → {past_dates[-1][0]}")
    print()

    # Check existing
    existing_ids = set(
        r.get("_id") or r.get("hkjc_race_id") or ""
        for r in db.db["races"].find({"venue": "ST"}, {"_id": 1, "hkjc_race_id": 1})
    )

    skipped_already = 0
    to_scrape = []

    for date_str, race_count in past_dates:
        for race_no in range(1, race_count + 1):
            race_id = f"{date_str.replace('-', '/')}_ST_{race_no}"
            if race_id not in existing_ids:
                to_scrape.append((date_str, race_no))
            else:
                skipped_already += 1

    print(f"Already scraped: {skipped_already}")
    print(f"Need to scrape: {len(to_scrape)}")
    print()

    # Group by date for progress display
    dates_to_scrape = sorted(set(d[0] for d in to_scrape))
    print(f"Will scrape {len(dates_to_scrape)} race dates")

    updated = 0
    errors = 0
    zero_results = []

    async def run_scraping():
        nonlocal updated, errors, zero_results

        async with RaceResultsScraper(headless=True) as scraper:
            for date_str in dates_to_scrape:
                races_for_date = [(d, rn) for d, rn in to_scrape if d == date_str]
                print(f"\n🔍 {date_str}: {len(races_for_date)} races")

                for date_iso, race_no in races_for_date:
                    parts = date_iso.split("-")
                    date_hkjc = f"{parts[0]}/{parts[1]}/{parts[2]}"
                    race_id = f"{date_hkjc}_ST_{race_no}"

                    print(f"   R{race_no}...", end=" ", flush=True)

                    try:
                        result = await scraper.scrape_race(date_hkjc, "ST", race_no)
                        if result:
                            meta = result.get("metadata", {})
                            horse_count = len(result.get("results", []))
                            await scraper.save_to_mongodb(result)
                            print(f"✅ {meta.get('distance', '?')}m | {horse_count} horses")
                            updated += 1
                            if horse_count == 0:
                                zero_results.append(race_id)
                        else:
                            print("⚠️  None")
                            errors += 1
                    except Exception as e:
                        print(f"❌ {e}")
                        errors += 1

                    await asyncio.sleep(0.8)  # polite delay

    asyncio.run(run_scraping())
    db.disconnect()

    print()
    print("=" * 60)
    print(f"  ✅ Scraped:    {updated} races")
    print(f"  ⚠️  0 horses:  {len(zero_results)} races (Group races?)")
    print(f"  ❌ Errors:     {errors}")
    print("=" * 60)

    if zero_results:
        print(f"\n  Races with 0 results (likely Group/G1 races):")
        for r in zero_results[:20]:
            print(f"    {r}")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
