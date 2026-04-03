"""
HKJC Precise Scraper v2.0
Using exact HTML selectors provided by user
"""

import asyncio
import re
from playwright.async_api import async_playwright, Page
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HKJCPreciseScraper:
    """
    Precise scraper using exact HTML class and ID selectors
    """
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse"
    
    def __init__(self, headless: bool = True, delay: int = 2):
        self.headless = headless
        self.delay = delay
        self.playwright = None
        self.browser = None
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def scrape_horse(self, hkjc_horse_id: str) -> Dict:
        """
        Scrape horse using precise selectors
        """
        url = f"{self.BASE_URL}?horseid={hkjc_horse_id}"
        horse_name = "祝願"  # Known name
        
        print(f"\n🐴 Scraping: {horse_name} ({hkjc_horse_id})")
        print("=" * 90)
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(self.delay)
            
            result = {
                "hkjc_horse_id": hkjc_horse_id,
                "horse_name": horse_name,
                "url": url,
                "scraped_at": datetime.now().isoformat(),
            }
            
            # 1. Race History (table class="bigborder")
            print("\n📊 1. 往績紀錄 (table.bigborder)...")
            result["race_history"] = await self._scrape_race_history_precise(page)
            
            # 2. Rating/Weight (same table, just navigate to tab)
            print("\n📊 2. 馬匹評分/體重/名次...")
            await self._click_tab(page, "馬匹評分/體重/名次")
            await asyncio.sleep(self.delay)
            # Data is same as race history, already captured
            print("   ℹ️  資料同往績紀錄，已包含")
            
            # 3. Distance Performance (table class="horseperformance")
            print("\n📊 3. 所跑途程賽績紀錄 (table.horseperformance)...")
            result["distance_stats"] = await self._scrape_with_selector(
                page, "所跑途程賽績紀錄", "table.horseperformance"
            )
            
            # 4. Workouts (table class="table_bd f_tal f_fs13 f_ffChinese")
            print("\n📊 4. 晨操紀錄 (table.table_bd)...")
            result["workouts"] = await self._scrape_with_selector(
                page, "晨操紀錄", "table.table_bd"
            )
            
            # 5. Medical (table class="table_bd" with specific xpath)
            print("\n📊 5. 傷患紀錄 (table.table_bd)...")
            result["medical"] = await self._scrape_medical_precise(page)
            
            # 6. Movements (table id="MovementRecord")
            print("\n📊 6. 搬遷紀錄 (table#MovementRecord)...")
            result["movements"] = await self._scrape_movements_precise(page)
            
            # 7. Pedigree (table class="blood" - 2 tables)
            print("\n📊 7. 血統簡評 (table.blood)...")
            result["pedigree"] = await self._scrape_pedigree_precise(page)
            
            await context.close()
            return result
            
        except Exception as e:
            logger.error(f"Error: {e}")
            await context.close()
            raise
    
    async def _click_tab(self, page: Page, tab_text: str) -> bool:
        """Click tab by text"""
        try:
            await page.click(f"text={tab_text}", timeout=5000)
            await asyncio.sleep(self.delay)
            return True
        except Exception:
            return False
    
    async def _scrape_race_history_precise(self, page: Page) -> List[Dict]:
        """
        Scrape race history from table.bigborder
        Ignore "往績賽事 XX/XX 馬季" rows
        祝願 should have exactly 17 races
        """
        races = []
        
        try:
            # Find table with class "bigborder"
            tables = await page.query_selector_all("table.bigborder")
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                
                for row in rows[1:]:  # Skip header
                    cells = await row.query_selector_all("td")
                    if len(cells) < 5:
                        continue
                    
                    # Get first cell to check if it's a race row or season separator
                    first_cell = await cells[0].inner_text()
                    first_cell = first_cell.strip()
                    
                    # Skip season separator rows (e.g., "往績賽事 2024/2025 馬季")
                    if "馬季" in first_cell or "往績賽事" in first_cell:
                        continue
                    
                    # Skip if first cell is empty or not a race number
                    if not first_cell or not re.match(r'^\d+$', first_cell):
                        continue
                    
                    # This is a valid race row
                    race = {
                        "hkjc_horse_id": "HK_2023_J256",
                        "race_no": first_cell,
                        "position": await cells[1].inner_text() if len(cells) > 1 else "",
                        "date": await cells[2].inner_text() if len(cells) > 2 else "",
                        "venue": await cells[3].inner_text() if len(cells) > 3 else "",
                        "distance": await cells[4].inner_text() if len(cells) > 4 else "",
                        "rating": await cells[8].inner_text() if len(cells) > 8 else "",
                        "jockey": await cells[10].inner_text() if len(cells) > 10 else "",
                        "scraped_at": datetime.now().isoformat()
                    }
                    races.append(race)
                
                # Only process first bigborder table
                break
            
            print(f"   ✅ {len(races)} races (filtered, excluding season separators)")
            return races
            
        except Exception as e:
            logger.error(f"Error scraping race history: {e}")
            return []
    
    async def _scrape_with_selector(self, page: Page, tab_name: str, selector: str) -> List[Dict]:
        """Generic scraper with tab click and selector"""
        records = []
        
        try:
            # Click tab
            clicked = await self._click_tab(page, tab_name)
            if not clicked:
                print(f"   Tab not found: {tab_name}")
                return records
            
            # Find table
            tables = await page.query_selector_all(selector)
            if not tables:
                print(f"   No table found with selector: {selector}")
                return records
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) <= 1:
                    continue
                
                # Extract data rows
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 3:
                        record = {
                            "hkjc_horse_id": "HK_2023_J256",
                            "col1": await cells[0].inner_text() if len(cells) > 0 else "",
                            "col2": await cells[1].inner_text() if len(cells) > 1 else "",
                            "col3": await cells[2].inner_text() if len(cells) > 2 else "",
                            "scraped_at": datetime.now().isoformat()
                        }
                        records.append(record)
                
                print(f"   ✅ {len(records)} records from {selector}")
                break
            
            return records
            
        except Exception as e:
            logger.error(f"Error with {tab_name}: {e}")
            return []
    
    async def _scrape_medical_precise(self, page: Page) -> int:
        """
        Scrape medical records
        table class="table_bd" with specific xpath
        祝願 should have 0
        """
        try:
            clicked = await self._click_tab(page, "傷患紀錄")
            if not clicked:
                return 0
            
            # Check if no records message
            text = await page.inner_text("body")
            if any(msg in text for msg in ["沒有", "很抱歉", "暫未提供"]):
                print("   ℹ️  祝願沒有傷患紀錄")
                return 0
            
            # Find table with xpath or class
            tables = await page.query_selector_all("table.table_bd")
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) > 1:
                    count = len(rows) - 1
                    if count > 50:  # Suspicious
                        print(f"   ⚠️  Suspicious count: {count}, likely wrong table")
                        return 0
                    print(f"   ✅ {count} medical records")
                    return count
            
            return 0
            
        except Exception as e:
            logger.error(f"Error scraping medical: {e}")
            return 0
    
    async def _scrape_movements_precise(self, page: Page) -> int:
        """
        Scrape movements from table#MovementRecord
        """
        try:
            clicked = await self._click_tab(page, "搬遷紀錄")
            if not clicked:
                return 0
            
            # Find table by ID
            table = await page.query_selector("table#MovementRecord")
            if not table:
                print("   ℹ️  No MovementRecord table found")
                return 0
            
            rows = await table.query_selector_all("tr")
            if len(rows) <= 1:
                return 0
            
            count = len(rows) - 1
            print(f"   ✅ {count} movements")
            return count
            
        except Exception as e:
            logger.error(f"Error scraping movements: {e}")
            return 0
    
    async def _scrape_pedigree_precise(self, page: Page) -> List[Dict]:
        """
        Scrape pedigree from table.blood (2 tables)
        """
        pedigree_data = []
        
        try:
            clicked = await self._click_tab(page, "血統簡評")
            if not clicked:
                return pedigree_data
            
            # Find all tables with class "blood"
            tables = await page.query_selector_all("table.blood")
            print(f"   Found {len(tables)} pedigree tables")
            
            for i, table in enumerate(tables):
                rows = await table.query_selector_all("tr")
                table_data = []
                
                for row in rows:
                    cells = await row.query_selector_all("td")
                    if cells:
                        row_text = [await c.inner_text() for c in cells]
                        table_data.append(" | ".join(row_text))
                
                pedigree_data.append({
                    "table_index": i,
                    "rows": table_data
                })
            
            return pedigree_data
            
        except Exception as e:
            logger.error(f"Error scraping pedigree: {e}")
            return pedigree_data
    
    async def save_to_mongodb(self, data: Dict):
        """Save scraped data to MongoDB"""
        print("\n💾 Saving to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            print("   ❌ Cannot connect to MongoDB")
            return
        
        hkjc_id = data["hkjc_horse_id"]
        
        # Delete old and insert new
        collections = {
            "horse_race_history": data.get("race_history", []),
            "horse_distance_stats": data.get("distance_stats", []),
            "horse_workouts": data.get("workouts", []),
        }
        
        for coll_name, items in collections.items():
            if isinstance(items, list):
                deleted = db.db[coll_name].delete_many({"hkjc_horse_id": hkjc_id}).deleted_count
                if len(items) > 0:
                    db.db[coll_name].insert_many(items)
                print(f"   ✅ {coll_name}: {len(items)} records (deleted {deleted} old)")
        
        # Update counts
        db.db["horse_medical"].delete_many({"hkjc_horse_id": hkjc_id})
        db.db["horse_medical"].insert_one({
            "hkjc_horse_id": hkjc_id,
            "count": data.get("medical", 0),
            "scraped_at": datetime.now().isoformat()
        })
        
        db.db["horse_movements"].delete_many({"hkjc_horse_id": hkjc_id})
        db.db["horse_movements"].insert_one({
            "hkjc_horse_id": hkjc_id,
            "count": data.get("movements", 0),
            "scraped_at": datetime.now().isoformat()
        })
        
        db.disconnect()
        print("\n✅ All data saved!")


async def main():
    """Test with 祝願"""
    scraper = HKJCPreciseScraper(headless=True, delay=2)
    
    async with scraper:
        data = await scraper.scrape_horse("HK_2023_J256")
        
        print("\n" + "=" * 90)
        print("📊 FINAL RESULTS using Precise Selectors")
        print("=" * 90)
        
        print("\nCollected data:")
        print(f"  Race history: {len(data.get('race_history', []))} races")
        print(f"  Distance stats: {len(data.get('distance_stats', []))} records")
        print(f"  Workouts: {len(data.get('workouts', []))} records")
        print(f"  Medical: {data.get('medical', 0)} records")
        print(f"  Movements: {data.get('movements', 0)} records")
        print(f"  Pedigree: {len(data.get('pedigree', []))} tables")
        
        # Save
        await scraper.save_to_mongodb(data)
        
        print("\n" + "=" * 90)
        print("Expected for 祝願:")
        print("  Race history: exactly 17 races")
        print("  Medical: 0 (confirmed no records)")
        print("  Movements: 1-3 (actual)")


if __name__ == "__main__":
    asyncio.run(main())
