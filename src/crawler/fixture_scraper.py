"""
HKJC Fixture Scraper
Download race meeting calendar to MongoDB
"""

import asyncio
import re
from playwright.async_api import async_playwright
from typing import List, Dict
from datetime import datetime
import sys
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

# Months to fetch (full season: Sep - Jul)
MONTHS = [
    ("2025", "09"), ("2025", "10"), ("2025", "11"), ("2025", "12"),
    ("2026", "01"), ("2026", "02"), ("2026", "03"), ("2026", "04"), 
    ("2026", "05"), ("2026", "06"), ("2026", "07")
]

FIXTURE_URL = "https://racing.hkjc.com/zh-hk/local/information/fixture"


class FixtureScraper:
    """Scrape HKJC race fixture/calendar"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        
    async def parse_month(self, year: str, month: str) -> List[Dict]:
        """Parse fixture for a specific month"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            
            url = f"{FIXTURE_URL}?calyear={year}&calm={month}"
            logger.info(f"Fetching: {url}")
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                
                table = await page.query_selector("table.table_bd")
                if not table:
                    logger.warning(f"No table found for {year}-{month}")
                    await browser.close()
                    return []
                
                rows = await table.query_selector_all("tr")
                
                race_meetings = []
                current_month = int(month)
                
                for row in rows:
                    cells = await row.query_selector_all("td")
                    
                    for cell in cells:
                        text = await cell.inner_text()
                        
                        # Skip header rows
                        if '星期' in text:
                            continue
                        
                        # Find race numbers
                        race_nums = re.findall(r'\((\d+)\)', text)
                        if race_nums:
                            # Find date
                            date_match = re.search(r'^(\d{1,2})', text.strip())
                            if date_match and current_month:
                                day = int(date_match.group(1))
                                
                                # Venue: "田" = ST, "谷" = HV
                                venue = 'ST'
                                if '谷' in text:
                                    venue = 'HV'
                                
                                race_count = max(int(r) for r in race_nums)
                                
                                race_meetings.append({
                                    'date': f"{year}-{current_month:02d}-{day:02d}",
                                    'venue': venue,
                                    'race_count': race_count,
                                    'source_url': FIXTURE_URL,
                                    'racecard_url': f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={year}/{month}/{day:02d}&Racecourse={venue}",
                                    'results_url': f"https://racing.hkjc.com/zh-hk/racing/information/English/Racing/LocalResults.aspx?RaceDate={year}-{current_month:02d}-{day:02d}",
                                    'scrape_status': 'pending',
                                    'created_at': datetime.now(),
                                    'modified_at': datetime.now()
                                })
                
            except Exception as e:
                logger.error(f"Error fetching {year}-{month}: {e}")
            finally:
                await browser.close()
            
            return race_meetings
    
    async def scrape_all(self) -> List[Dict]:
        """Scrape all months"""
        all_meetings = []
        
        for year, month in MONTHS:
            logger.info(f"Processing {year}-{month}...")
            meetings = await self.parse_month(year, month)
            logger.info(f"  Found {len(meetings)} meetings")
            all_meetings.extend(meetings)
        
        return all_meetings
    
    def save_to_mongodb(self, meetings: List[Dict]) -> bool:
        """Save fixtures to MongoDB"""
        logger.info(f"Saving {len(meetings)} fixtures to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            logger.error("Cannot connect to MongoDB")
            return False
        
        # Clear and insert
        db.db["fixtures"].delete_many({})
        if meetings:
            db.db["fixtures"].insert_many(meetings)
        
        count = db.db["fixtures"].count_documents({})
        logger.info(f"Fixtures in DB: {count}")
        
        db.disconnect()
        return True


async def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    scraper = FixtureScraper(headless=True)
    meetings = await scraper.scrape_all()
    scraper.save_to_mongodb(meetings)
    
    print("\n" + "=" * 60)
    print("📊 FIXTURE SCRAPER COMPLETE")
    print("=" * 60)
    print(f"Total meetings: {len(meetings)}")


if __name__ == "__main__":
    asyncio.run(main())
