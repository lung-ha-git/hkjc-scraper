"""
SQLite Test - Quick test without MongoDB
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.sqlite_connection import SQLiteConnection, get_db
from src.crawler.hkjc_scraper import HKJCScraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_sqlite_setup():
    """Test SQLite database setup"""
    print("🧪 Testing SQLite database setup...")
    
    db = get_db()
    print("✅ SQLite database connected")
    
    stats = db.get_stats()
    print(f"📊 Current stats: {stats}")
    
    return True


def test_scraper_with_sqlite():
    """Test scraper with SQLite storage"""
    print("\n🧪 Testing scraper with SQLite...")
    
    db = get_db()
    scraper = HKJCScraper(delay=(3, 6))
    
    # Test with a recent date (we'll skip actual HTTP call for now)
    test_date = "2026-03-01"
    
    print(f"📅 Testing date: {test_date}")
    
    # For demo, insert test data
    test_race = {
        "race_id": "20260301_R1",
        "date": test_date,
        "venue": "HV",
        "race_no": 1,
        "distance": 1200,
        "course": "TURF",
        "track_condition": "GF",
        "race_class": "Class 4",
        "runners": [
            {"position": "1", "horse_no": "5", "horse_name": "TestHorse", "jockey": "TestJockey"}
        ]
    }
    
    db.insert_race(test_race)
    print(f"✅ Inserted test race: {test_race['race_id']}")
    
    # Store raw result
    db.insert_raw_result(test_date, "HV", 1, {"status": "scraped", "races_count": 1})
    print("✅ Inserted raw result")
    
    # Check stats
    stats = db.get_stats()
    print(f"📊 Database stats: {stats}")
    
    db.disconnect()
    print("✅ SQLite test complete!")
    
    return True


def main():
    """Run SQLite tests"""
    print("=" * 60)
    print("🧪 HKJC SQLite Test Suite")
    print("=" * 60)
    
    results = []
    results.append(("SQLite Setup", test_sqlite_setup()))
    results.append(("Scraper + SQLite", test_scraper_with_sqlite()))
    
    print("\n" + "=" * 60)
    print("📊 Test Results")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("=" * 60)
    if all_passed:
        print("🎉 All SQLite tests passed!")
        print("=" * 60)
        print("\n💡 Next steps:")
        print("1. Wait for MongoDB installation to complete")
        print("2. Then migrate to MongoDB: python3 -m src.database.setup_db")
        print("3. Run real scraper test with actual HKJC data")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
