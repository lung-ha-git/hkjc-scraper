"""Denormalize race_results into races.results for ST races.

race_results_scraper saves to races._id (not races.race_id field).
Need to match races._id with race_results.race_id.
"""
import sys
sys.path.insert(0, "/app")
from src.database.connection import DatabaseConnection

db = DatabaseConnection()
db.connect()

st_races = list(db.db["races"].find({"venue": "ST"}))
print(f"Found {len(st_races)} ST races")

updated = 0
skipped_no_match = 0

for race in st_races:
    # race_results use _id format (e.g. "2026/03/22_ST_10")
    doc_id = race.get("_id")
    if not doc_id:
        skipped_no_match += 1
        continue

    # Query race_results by race_id field
    race_results_docs = list(db.db["race_results"].find({"race_id": doc_id}))

    if race_results_docs:
        db.db["races"].update_one(
            {"_id": doc_id},
            {"$set": {"results": race_results_docs}}
        )
        updated += 1
        if updated % 10 == 0:
            print(f"  Updated {updated}...")
    else:
        skipped_no_match += 1

print(f"Updated {updated} ST races with results")
print(f"Skipped {skipped_no_match} (no matching race_results)")
db.disconnect()
