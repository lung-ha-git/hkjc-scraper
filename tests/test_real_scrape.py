"""
Test HKJC Scraper with Real Data + MongoDB Storage
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.crawler.hkjc_scraper import HKJCScraper
from src.database.connection import DatabaseConnection
import logging
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_real_scrape():
    """Test scraper with real HKJC data"""
    print("🚀 Starting real data scrape test...")
    print("=" * 60)
    
    # Connect to MongoDB
    db = DatabaseConnection()
    if not db.connect():
        print("❌ Cannot connect to MongoDB")
        return False
    
    # Initialize scraper
    scraper = HKJCScraper(delay=(3, 6))
    
    # Test date - use a historical race day
    # Recent race dates in 2025: check Sundays and Wednesdays
    test_date = "2025-12-28"  # Last Sunday of 2025
    
    print(f"📅 Fetching data for: {test_date}")
    print("⏳ This may take 30-60 seconds...")
    
    try:
        # Fetch race results
        races = scraper.get_race_results(test_date)
        
        if not races:
            print(f"⚠️  No races found for {test_date}")
            print("💡 This could be because:")
            print("   - No race on this date")
            print("   - HKJC website structure changed")
            print("   - Rate limiting or connection issue")
            return False
        
        print(f"✅ Found {len(races)} races!")
        
        # Store in MongoDB
        for race in races:
            # Insert into raw_results
            db.raw_results.insert_one({
                "date": race['date'],
                "venue": race['venue'],
                "race_no": race['race_no'],
                "data": race,
                "scraped_at": datetime.now()
            })
            
            # Insert into races collection
            db.races.insert_one(race)
            
            print(f"  ✅ Stored Race {race['race_no']}: {len(race.get('runners', []))} runners")
        
        # Show stats
        stats = db.get_stats()
        print("\n📊 Database Stats:")
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        db.disconnect()
        
        print("\n✅ Real scrape test complete!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Scrape failed: {e}", exc_info=True)
        db.disconnect()
        return False


def main():
    """Run scraper test"""
    print("🧪 HKJC Real Data Scraper Test")
    print("=" * 60)
    
    success = test_real_scrape()
    
    print("=" * 60)
    if success:
        print("🎉 Success! Real data scraped and stored in MongoDB")
    else:
        print("⚠️  Test completed with warnings")
        print("   Check logs above for details")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
