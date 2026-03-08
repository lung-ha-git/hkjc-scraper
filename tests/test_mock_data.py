"""
Test Scraper with Mock Data + MongoDB
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.mock_data import MockHKJCGenerator
from src.database.connection import DatabaseConnection
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_with_mock_data():
    """Test with generated mock data"""
    print("🚀 Testing with MOCK data...")
    print("=" * 60)
    
    # Connect to MongoDB
    db = DatabaseConnection()
    if not db.connect():
        print("❌ Cannot connect to MongoDB")
        return False
    
    # Generate mock data
    generator = MockHKJCGenerator()
    test_date = "2025-12-28"
    
    print(f"📅 Generating mock data for: {test_date}")
    races = generator.generate_race_day(test_date, venue="ST")
    
    print(f"✅ Generated {len(races)} races!")
    
    # Store in MongoDB
    for race in races:
        # Insert into raw_results
        db.raw_results.insert_one({
            "date": race['date'],
            "venue": race['venue'],
            "race_no": race['race_no'],
            "data": race,
            "scraped_at": datetime.now(),
            "source": "mock"
        })
        
        # Insert into races collection
        db.races.insert_one(race)
        
        print(f"  ✅ Stored Race {race['race_no']}: {len(race['runners'])} runners")
    
    # Show sample data
    print("\n📋 Sample Race Data:")
    sample_race = races[0]
    print(f"  Race {sample_race['race_no']}: {sample_race['distance']}m, {sample_race['track_condition']}")
    print(f"  Runners: {len(sample_race['runners'])}")
    for runner in sample_race['runners'][:3]:
        print(f"    {runner['position']}. {runner['horse_name']} ({runner['jockey']}) - {runner['finish_time']}")
    
    # Show stats
    stats = db.get_stats()
    print("\n📊 Database Stats:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    db.disconnect()
    
    print("\n✅ Mock data test complete!")
    return True


def main():
    """Run mock data test"""
    print("🧪 HKJC Mock Data Test")
    print("=" * 60)
    
    success = test_with_mock_data()
    
    print("=" * 60)
    if success:
        print("🎉 Success! Mock data stored in MongoDB")
        print("\nNext steps:")
        print("1. Test ETL pipeline")
        print("2. Query and analyze data")
        print("3. Build API endpoints")
    else:
        print("⚠️  Test failed")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
