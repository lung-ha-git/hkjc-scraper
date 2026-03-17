"""
Test Horse Ratings Scraper
Tests the ratingresultweight page scraping
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from src.crawler.complete_horse_scraper import CompleteHorseScraper
from src.database.connection import DatabaseConnection
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_rating_scraper():
    """Test scraping horse ratings from ratingresultweight page"""
    print("=" * 70)
    print("🦄 Testing Horse Ratings Scraper")
    print("=" * 70)
    
    # Test horse IDs - try a few known horses
    test_horses = [
        "HK_2023_J256",  # 祝願
        "HK_2023_B389",  # 速遞王牌
    ]
    
    scraper = CompleteHorseScraper(headless=False, delay=2)
    
    for horse_id in test_horses:
        print(f"\n🐴 Testing horse: {horse_id}")
        print("-" * 50)
        
        try:
            result = await scraper.scrape_horse_complete(horse_id)
            
            if result:
                print(f"✅ Successfully scraped {horse_id}")
                print(f"   - Basic info: {result.get('basic_info', {}).get('name', 'N/A')}")
                print(f"   - Race history: {len(result.get('race_history', []))} races")
                print(f"   - Ratings: {len(result.get('ratings', []))} records")
                
                # Check MongoDB
                db = DatabaseConnection()
                if db.connect():
                    ratings_count = db.db["horse_ratings"].count_documents({
                        "hkjc_horse_id": horse_id
                    })
                    print(f"   - Ratings in DB: {ratings_count}")
                    db.disconnect()
            else:
                print(f"❌ No data returned for {horse_id}")
                
        except Exception as e:
            print(f"❌ Error scraping {horse_id}: {e}")
        
        # Only test one horse in headless mode for CI
        if scraper.headless:
            break
    
    print("\n" + "=" * 70)
    print("✅ Test complete!")
    print("=" * 70)


async def test_rating_page_direct():
    """Direct test of rating extraction (without full horse scrape)"""
    print("\n" + "=" * 70)
    print("🔬 Direct Rating Page Test")
    print("=" * 70)
    
    from playwright.async_api import async_playwright
    
    horse_id = "HK_2023_J256"
    url = f"https://racing.hkjc.com/zh-hk/local/information/ratingresultweight?horseid={horse_id}"
    
    print(f"\n📄 Testing URL: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        # Get page title
        title = await page.title()
        print(f"📄 Page title: {title}")
        
        # Find tables
        tables = await page.query_selector_all("table")
        print(f"📊 Found {len(tables)} tables")
        
        # Look for rating table
        for i, table in enumerate(tables):
            rows = await table.query_selector_all("tr")
            if len(rows) > 10:
                row2_text = await rows[2].inner_text() if len(rows) > 2 else ""
                if "評分" in row2_text:
                    print(f"✅ Found rating table at index {i}")
                    print(f"   Rows: {len(rows)}")
                    
                    # Get first data row to count columns
                    first_row = await rows[1].query_selector_all("td")
                    print(f"   Columns (races): {len(first_row) - 1}")  # Minus header column
                    break
        
        await browser.close()
    
    print("=" * 70)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test horse ratings scraper")
    parser.add_argument("--direct", action="store_true", help="Run direct page test only")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")
    args = parser.parse_args()
    
    if args.direct:
        asyncio.run(test_rating_page_direct())
    else:
        asyncio.run(test_rating_scraper())
