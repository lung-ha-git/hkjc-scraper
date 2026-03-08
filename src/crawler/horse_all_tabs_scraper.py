"""
Complete Horse All Tabs Scraper
Scrapes all tabs: 往績、途程、晨操、傷患、搬遷、海外、彩衣
"""

import asyncio
import re
from playwright.async_api import async_playwright, Page
from datetime import datetime
from typing import Dict, List, Optional
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class HorseAllTabsScraper:
    """
    Complete scraper for all horse detail tabs
    Scrapes: race_history, distance_stats, workouts, medical, movements, overseas, jersey
    """
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse"
    
    # Tab mapping (text on tab -> internal key)
    TAB_MAPPING = {
        "往績紀錄": "race_history",
        "所跑途程賽績紀錄": "distance_stats",
        "晨操紀錄": "workouts",
        "傷患紀錄": "medical",
        "搬遷紀錄": "movements",
        "海外賽績紀錄": "overseas",
        "血統簡評": "pedigree",
    }
    
    def __init__(self, headless: bool = True, delay: int = 3):
        self.headless = headless
        self.delay = delay
        self.hkjc_horse_id = None
        self.page = None
        self.context = None
        self.browser = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def scrape_horse(self, hkjc_horse_id: str) -> Dict:
        """
        Scrape all tabs for a horse
        
        Args:
            hkjc_horse_id: e.g., "HK_2023_J256"
            
        Returns:
            Dict with all scraped data
        """
        self.hkjc_horse_id = hkjc_horse_id
        url = f"{self.BASE_URL}?horseid={hkjc_horse_id}"
        
        print(f"\n🐴 Starting complete scrape for: {hkjc_horse_id}")
        print("=" * 80)
        
        self.page = await self.context.new_page()
        
        try:
            # Load initial page (shows race history by default)
            print(f"\n📱 Loading: {url}")
            await self.page.goto(url, wait_until="networkidle")
            await self.page.wait_for_timeout(self.delay * 1000)
            
            result = {
                "hkjc_horse_id": hkjc_horse_id,
                "url": url,
                "scraped_at": datetime.now().isoformat(),
            }
            
            # Scrape race history (default tab)
            print("\n📊 1. Scraping 往績紀錄 (default tab)...")
            result["race_history"] = await self._scrape_race_history()
            print(f"   ✅ {len(result['race_history'])} races scraped")
            
            # Find and click other tabs
            for tab_text, key in self.TAB_MAPPING.items():
                if key == "race_history":
                    continue  # Already done
                
                print(f"\n📊 {key.upper()}. Scraping {tab_text}...")
                
                try:
                    clicked = await self._click_tab(tab_text)
                    if clicked:
                        await self.page.wait_for_timeout(self.delay * 1000)
                        
                        if key == "distance_stats":
                            result[key] = await self._scrape_distance_stats()
                        elif key == "workouts":
                            result[key] = await self._scrape_workouts()
                        elif key == "medical":
                            result[key] = await self._scrape_medical()
                        elif key == "movements":
                            result[key] = await self._scrape_movements()
                        elif key == "overseas":
                            result[key] = await self._scrape_overseas()
                        elif key == "pedigree":
                            result[key] = await self._scrape_pedigree()
                        
                        print(f"   ✅ {len(result[key]) if isinstance(result[key], list) else 'data'} scraped")
                    else:
                        print(f"   ⚠️  Tab not found: {tab_text}")
                        result[key] = []
                
                except Exception as e:
                    logger.error(f"Error scraping {tab_text}: {e}")
                    result[key] = {"error": str(e)}
            
            await self.page.close()
            return result
            
        except Exception as e:
            logger.error(f"Error in scrape_horse: {e}")
            await self.page.close()
            raise
    
    async def _click_tab(self, tab_text: str) -> bool:
        """Click on a tab by text"""
        try:
            # Try different selectors
            selectors = [
                f"text='{tab_text}'",
                f"a:has-text('{tab_text}')",
                f"[role='tab']:has-text('{tab_text}')",
            ]
            
            for selector in selectors:
                try:
                    if await self.page.is_visible(selector, timeout=2000):
                        # Check if already active
                        element = await self.page.query_selector(selector)
                        classes = await element.get_attribute("class")
                        if classes and "active" in classes:
                            return True  # Already on this tab
                        
                        await self.page.click(selector)
                        return True
                except:
                    continue
            
            # Manual search
            all_clickable = await self.page.query_selector_all("a, button, [role='tab'], li")
            for elem in all_clickable:
                text = await elem.inner_text()
                if tab_text in text:
                    await elem.click()
                    return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Could not click tab {tab_text}: {e}")
            return False
    
    async def _scrape_race_history(self) -> List[Dict]:
        """Scrape race history table"""
        races = []
        
        try:
            tables = await self.page.query_selector_all("table")
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) < 5:
                    continue
                
                header_cells = await rows[0].query_selector_all("th, td")
                header_text = await header_cells[0].inner_text() if len(header_cells) > 0 else ""
                
                if "場次" in header_text:
                    headers = [await c.inner_text() for c in header_cells]
                    
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 10:
                            race_data = {
                                "hkjc_horse_id": self.hkjc_horse_id,
                                "scraped_at": datetime.now().isoformat()
                            }
                            
                            for j, cell in enumerate(cells):
                                val = await cell.inner_text()
                                if j < len(headers):
                                    header = headers[j].strip().replace('\n', '_').replace('/', '_')
                                    race_data[header] = val.strip() if val else ""
                            
                            races.append(race_data)
                    
                    break
        
        except Exception as e:
            logger.error(f"Error in _scrape_race_history: {e}")
        
        return races
    
    async def _scrape_distance_stats(self) -> List[Dict]:
        """Scrape distance analysis stats"""
        stats = []
        
        try:
            tables = await self.page.query_selector_all("table")
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows[1:]:  # Skip header
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 4:
                        stat = {
                            "hkjc_horse_id": self.hkjc_horse_id,
                            "distance": await cells[0].inner_text() if len(cells) > 0 else "",
                            "starts": await cells[1].inner_text() if len(cells) > 1 else "",
                            "wins": await cells[2].inner_text() if len(cells) > 2 else "",
                            "places": await cells[3].inner_text() if len(cells) > 3 else "",
                            "scraped_at": datetime.now().isoformat()
                        }
                        if stat["distance"]:
                            stats.append(stat)
        
        except Exception as e:
            logger.error(f"Error in _scrape_distance_stats: {e}")
        
        return stats
    
    async def _scrape_workouts(self) -> List[Dict]:
        """Scrape workout/gallop records"""
        workouts = []
        
        try:
            tables = await self.page.query_selector_all("table")
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 5:
                        workout = {
                            "hkjc_horse_id": self.hkjc_horse_id,
                            "date": await cells[0].inner_text() if len(cells) > 0 else "",
                            "venue": await cells[1].inner_text() if len(cells) > 1 else "",
                            "distance": await cells[2].inner_text() if len(cells) > 2 else "",
                            "time": await cells[3].inner_text() if len(cells) > 3 else "",
                            "rider": await cells[4].inner_text() if len(cells) > 4 else "",
                            "scraped_at": datetime.now().isoformat()
                        }
                        if workout["date"]:
                            workouts.append(workout)
        
        except Exception as e:
            logger.error(f"Error in _scrape_workouts: {e}")
        
        return workouts
    
    async def _scrape_medical(self) -> List[Dict]:
        """Scrape medical/vet records"""
        records = []
        
        try:
            tables = await self.page.query_selector_all("table")
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 3:
                        record = {
                            "hkjc_horse_id": self.hkjc_horse_id,
                            "date": await cells[0].inner_text() if len(cells) > 0 else "",
                            "issue": await cells[1].inner_text() if len(cells) > 1 else "",
                            "treatment": await cells[2].inner_text() if len(cells) > 2 else "",
                            "scraped_at": datetime.now().isoformat()
                        }
                        if record["date"]:
                            records.append(record)
        
        except Exception as e:
            logger.error(f"Error in _scrape_medical: {e}")
        
        return records
    
    async def _scrape_movements(self) -> List[Dict]:
        """Scrape movement/location changes"""
        movements = []
        
        try:
            tables = await self.page.query_selector_all("table")
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 3:
                        movement = {
                            "hkjc_horse_id": self.hkjc_horse_id,
                            "date": await cells[0].inner_text() if len(cells) > 0 else "",
                            "from_location": await cells[1].inner_text() if len(cells) > 1 else "",
                            "to_location": await cells[2].inner_text() if len(cells) > 2 else "",
                            "reason": await cells[3].inner_text() if len(cells) > 3 else "",
                            "scraped_at": datetime.now().isoformat()
                        }
                        if movement["date"]:
                            movements.append(movement)
        
        except Exception as e:
            logger.error(f"Error in _scrape_movements: {e}")
        
        return movements
    
    async def _scrape_overseas(self) -> List[Dict]:
        """Scrape overseas race records"""
        races = []
        
        try:
            tables = await self.page.query_selector_all("table")
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 6:
                        race = {
                            "hkjc_horse_id": self.hkjc_horse_id,
                            "date": await cells[0].inner_text() if len(cells) > 0 else "",
                            "country": await cells[1].inner_text() if len(cells) > 1 else "",
                            "racecourse": await cells[2].inner_text() if len(cells) > 2 else "",
                            "position": await cells[3].inner_text() if len(cells) > 3 else "",
                            "distance": await cells[4].inner_text() if len(cells) > 4 else "",
                            "prize": await cells[5].inner_text() if len(cells) > 5 else "",
                            "scraped_at": datetime.now().isoformat()
                        }
                        if race["date"]:
                            races.append(race)
        
        except Exception as e:
            logger.error(f"Error in _scrape_overseas: {e}")
        
        return races
    
    async def _scrape_pedigree(self) -> Dict:
        """Scrape pedigree info (may be on same page)"""
        pedigree = {"hkjc_horse_id": self.hkjc_horse_id}
        
        try:
            text = await self.page.inner_text("body")
            
            # Extract pedigree info
            sire_match = re.search(r'父系\s*[:：]\s*([^\n]+)', text)
            dam_match = re.search(r'母系\s*[:：]\s*([^\n]+)', text)
            damsire_match = re.search(r'外祖父\s*[:：]\s*([^\n]+)', text)
            
            if sire_match:
                pedigree["sire"] = sire_match.group(1).strip()
            if dam_match:
                pedigree["dam"] = dam_match.group(1).strip()
            if damsire_match:
                pedigree["damsire"] = damsire_match.group(1).strip()
            
            pedigree["scraped_at"] = datetime.now().isoformat()
        
        except Exception as e:
            logger.error(f"Error in _scrape_pedigree: {e}")
        
        return pedigree
    
    async def save_to_mongodb(self, data: Dict):
        """Save all scraped data to MongoDB"""
        print("\n💾 Saving to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            print("   ❌ Cannot connect to MongoDB")
            return
        
        hkjc_id = data["hkjc_horse_id"]
        
        # Save each collection
        collections_data = {
            "horse_race_history": data.get("race_history", []),
            "horse_distance_stats": data.get("distance_stats", []),
            "horse_workouts": data.get("workouts", []),
            "horse_medical": data.get("medical", []),
            "horse_movements": data.get("movements", []),
            "horse_overseas": data.get("overseas", []),
        }
        
        for collection_name, items in collections_data.items():
            if items:
                # Delete old records
                deleted = db.db[collection_name].delete_many({"hkjc_horse_id": hkjc_id}).deleted_count
                # Insert new records
                if isinstance(items, list) and len(items) > 0:
                    db.db[collection_name].insert_many(items)
                    print(f"   ✅ {collection_name}: {len(items)} records (deleted {deleted} old)")
        
        # Update pedigree
        if data.get("pedigree"):
            db.db["horse_pedigree"].update_one(
                {"hkjc_horse_id": hkjc_id},
                {"$set": data["pedigree"]},
                upsert=True
            )
            print(f"   ✅ horse_pedigree: updated")
        
        db.disconnect()
        print("\n✅ All data saved!")


async def main():
    """Test the scraper"""
    scraper = HorseAllTabsScraper(headless=True, delay=3)
    
    async with scraper:
        hkjc_id = "HK_2023_J256"
        
        print(f"🚀 Testing complete scraper for: {hkjc_id}")
        
        try:
            data = await scraper.scrape_horse(hkjc_id)
            
            print("\n" + "=" * 80)
            print("📊 SCRAPE COMPLETE - Summary")
            print("=" * 80)
            
            for key, value in data.items():
                if key not in ["hkjc_horse_id", "url", "scraped_at"]:
                    if isinstance(value, list):
                        print(f"  {key}: {len(value)} records")
                    elif isinstance(value, dict):
                        if "error" in value:
                            print(f"  {key}: ⚠️  Error - {value['error']}")
                        else:
                            print(f"  {key}: ✓ data scraped")
            
            # Save to MongoDB
            await scraper.save_to_mongodb(data)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
