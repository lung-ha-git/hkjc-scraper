"""Denormalize race_results INTO races.results for ALL races (ST + HV)."""
import sys
sys.path.insert(0, "/app")
from src.database.connection import DatabaseConnection

db = DatabaseConnection()
db.connect()

# Denormalize for ALL races (both HV and ST)
# race_results.race_id == races._id
all_races = list(db.db["races"].find({}))
print(f"Total races to process: {len(all_races)}")

updated = 0
errors = 0
no_match = 0

for race in all_races:
    race_id = race.get("_id")
    if not race_id:
        continue

    # Query race_results by race_id
    race_results_docs = list(db.db["race_results"].find({"race_id": race_id}))

    if race_results_docs:
        # Also get payout from race_payouts
        payout_doc = db.db["race_payouts"].find_one({"race_id": race_id})
        payout = None
        if payout_doc:
            payout = payout_doc.get("pools")

        update = {"$set": {"results": race_results_docs}}
        if payout:
            update["$set"]["payout"] = payout

        db.db["races"].update_one({"_id": race_id}, update)
        updated += 1
        if updated % 200 == 0:
            print(f"  Updated {updated}...")
    else:
        no_match += 1

print(f"\n✅ Updated: {updated} races")
print(f"⚠️  No race_results match: {no_match} races")
db.disconnect()
