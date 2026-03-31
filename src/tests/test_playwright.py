"""
Test Playwright Scraper
Quick test to verify data extraction works
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.crawler.playwright_scraper import HKJCPlaywrightScraper
from src.database.connection import DatabaseConnection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_jockey_ranking():
    """Test scraping jockey rankings"""
    print("🏇 Testing Jockey Rankings Scrape...")
    print("=" * 60)
    
    async with HKJCPlaywrightScraper(headless=True, delay=3) as scraper:
        jockeys = await scraper.scrape_jockey_ranking()
        
        print(f"✅ Found {len(jockeys)} jockeys")
        
        if jockeys:
            print("\n📋 Sample data:")
            for jockey in jockeys[:5]:
                print(f"  - {jockey.get('name', 'N/A')}: {jockey.get('wins', '0')} wins")
        
        # Store in MongoDB
        if jockeys:
            db = DatabaseConnection()
            if db.connect():
                for jockey in jockeys:
                    db.jockeys.insert_one(jockey)
                print(f"\n💾 Stored {len(jockeys)} jockeys in MongoDB")
                db.disconnect()
        
        return len(jockeys) > 0


async def test_trainer_ranking():
    """Test scraping trainer rankings"""
    print("\n🏇 Testing Trainer Rankings Scrape...")
    print("=" * 60)
    
    async with HKJCPlaywrightScraper(headless=True, delay=3) as scraper:
        trainers = await scraper.scrape_trainer_ranking()
        
        print(f"✅ Found {len(trainers)} trainers")
        
        if trainers:
            print("\n📋 Sample data:")
            for trainer in trainers[:5]:
                print(f"  - {trainer.get('name', 'N/A')}: {trainer.get('wins', '0')} wins")
        
        # Store in MongoDB
        if trainers:
            db = DatabaseConnection()
            if db.connect():
                for trainer in trainers:
                    db.trainers.insert_one(trainer)
                print(f"\n💾 Stored {len(trainers)} trainers in MongoDB")
                db.disconnect()
        
        return len(trainers) > 0


async def main():
    """Run tests"""
    print("🧪 Playwright Scraper Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test jockey rankings
    try:
        jockey_success = await test_jockey_ranking()
        results.append(("Jockey Rankings", jockey_success))
    except Exception as e:
        print(f"❌ Jockey test failed: {e}")
        results.append(("Jockey Rankings", False))
    
    # Test trainer rankings
    try:
        trainer_success = await test_trainer_ranking()
        results.append(("Trainer Rankings", trainer_success))
    except Exception as e:
        print(f"❌ Trainer test failed: {e}")
        results.append(("Trainer Rankings", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("=" * 60)
    if all_passed:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests completed with issues")
        print("   Check logs above for details")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
