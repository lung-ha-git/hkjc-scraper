import asyncio
from src.crawler.complete_horse_scraper import CompleteHorseScraper
from src.database.connection import DatabaseConnection
import time
import sys

async def update():
    db = DatabaseConnection()
    db.connect()
    
    while True:
        try:
            old = list(db.db["horse_distance_stats"].find({"distance_performance.distance_1200": {"$exists": True}}).limit(20))
            if not old:
                print("All done!")
                break
            
            horse_ids = [h["hkjc_horse_id"] for h in old]
            print(f"Processing {len(horse_ids)} horses...")
            
            for horse_id in horse_ids:
                try:
                    scraper = CompleteHorseScraper(headless=True)
                    await scraper.scrape_horse_complete(horse_id)
                except Exception as e:
                    print(f"Error {horse_id}: {e}")
                    sys.stdout.flush()
                time.sleep(0.5)
        except Exception as e:
            print(f"Loop error: {e}")
            sys.stdout.flush()
            time.sleep(1)
    
    db.disconnect()
    print("All done!")

asyncio.run(update())
