import sys
sys.path.insert(0, "/app")
from src.database.connection import DatabaseConnection

db = DatabaseConnection()
db.connect()

all_races = list(db.db["races"].find({}))
print(f"Total: {len(all_races)} races")

updated = 0
no_match = 0
for race in all_races:
    race_id = race.get("_id")
    if not race_id:
        continue
    race_results_docs = list(db.db["race_results"].find({"race_id": race_id}))
    if race_results_docs:
        payout_doc = db.db["race_payouts"].find_one({"race_id": race_id})
        update = {"$set": {"results": race_results_docs}}
        if payout_doc and payout_doc.get("pools"):
            update["$set"]["payout"] = payout_doc["pools"]
        db.db["races"].update_one({"_id": race_id}, update)
        updated += 1

print(f"Updated: {updated}")
db.disconnect()
