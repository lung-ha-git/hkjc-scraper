"""
Test Race Card Scraper
Tests the racecard page scraping
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from src.crawler.racecard_scraper import RaceCardScraper
from src.database.connection import DatabaseConnection
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_single_race(race_date: str, venue: str, race_no: int):
    """Test scraping a single race"""
    print("=" * 70)
    print(f"🏇 Testing Race {race_no} ({venue})")
    print("=" * 70)
    
    async with RaceCardScraper(headless=True, delay=2) as scraper:
        url = scraper._build_url(race_date, venue, race_no)
        print(f"\n📄 URL: {url}")
        print("-" * 50)
        
        racecard = await scraper.scrape_race(race_date, venue, race_no)
        
        if racecard:
            print(f"\n✅ Race {racecard['race_no']}: {racecard.get('race_name', 'N/A')}")
            print(f"   Venue: {racecard.get('venue')}")
            print(f"   Time: {racecard.get('race_time', 'N/A')}")
            print(f"   Course: {racecard.get('course', 'N/A')}, Distance: {racecard.get('distance', 'N/A')}m")
            print(f"   Track: {racecard.get('track_condition', 'N/A')}")
            print(f"   Class: {racecard.get('class', 'N/A')}")
            print(f"   Horses: {len(racecard.get('horses', []))}")
            
            for horse in racecard.get('horses', [])[:5]:
                print(f"      {horse.get('horse_no')}. {horse.get('horse_name')} "
                      f"({horse.get('jockey_name')}) - 檔位:{horse.get('draw')}")
        else:
            print("❌ No race data found")
    
    print("\n" + "=" * 70)


async def test_race_day(race_date: str, venue: str):
    """Test scraping full race day"""
    print("=" * 70)
    print(f"🏇 Testing Race Day - {race_date} ({venue})")
    print("=" * 70)
    
    async with RaceCardScraper(headless=True, delay=2) as scraper:
        racecards = await scraper.scrape_race_day(race_date, venue)
        
        print(f"\n✅ Found {len(racecards)} races")
        
        for card in racecards:
            print(f"\n🏇 Race {card['race_no']}: {card.get('race_name', 'N/A')}")
            print(f"   Venue: {card.get('venue')}")
            print(f"   Time: {card.get('race_time', 'N/A')}")
            print(f"   Course: {card.get('course', 'N/A')}, Distance: {card.get('distance', 'N/A')}m")
            print(f"   Class: {card.get('class', 'N/A')}")
            print(f"   Horses: {len(card.get('horses', []))}")
    
    print("\n" + "=" * 70)


async def test_save_to_mongodb(race_date: str, venue: str):
    """Test saving to MongoDB"""
    print("=" * 70)
    print("💾 Testing Save to MongoDB")
    print("=" * 70)
    
    async with RaceCardScraper(headless=True, delay=2) as scraper:
        racecards = await scraper.scrape_race_day(race_date, venue)
        
        if racecards:
            success = scraper.save_to_mongodb(racecards)
            
            if success:
                print("✅ Saved to MongoDB!")
                
                db = DatabaseConnection()
                if db.connect():
                    count = db.db["racecards"].count_documents({
                        "race_date": race_date,
                        "venue": venue
                    })
                    print(f"   Race cards in DB: {count}")
                    db.disconnect()
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test race card scraper")
    parser.add_argument("--date", type=str, default="2026-03-18", help="Race date (YYYY-MM-DD)")
    parser.add_argument("--venue", type=str, default="HV", help="Venue: HV or ST")
    parser.add_argument("--race-no", type=int, help="Single race number")
    parser.add_argument("--save", action="store_true", help="Save to MongoDB")
    args = parser.parse_args()
    
    if args.race_no:
        asyncio.run(test_single_race(args.date, args.venue, args.race_no))
    elif args.save:
        asyncio.run(test_save_to_mongodb(args.date, args.venue))
    else:
        asyncio.run(test_race_day(args.date, args.venue))
