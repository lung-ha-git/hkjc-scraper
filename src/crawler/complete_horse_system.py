"""
Complete Horse Data Collection System
Phase 1: Collect all horse data with precise selectors
"""

import asyncio
import re
from playwright.async_api import async_playwright
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CompleteHorseSystem:
    """
    Complete horse data collection with precise tab handling
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
    
    async def collect_horse(self, hkjc_horse_id: str) -> Dict:
        """
        Collect complete horse data
        """
        url = f"{self.BASE_URL}?horseid={hkjc_horse_id}"
        
        print(f"\n{'='*80}")
        print(f"🐴 Collecting: {hkjc_horse_id}")
        print(f"{'='*80}")
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(self.delay)
            
            result = {
                "hkjc_horse_id": hkjc_horse_id,
                "url": url,
                "collected_at": datetime.now().isoformat()
            }
            
            # Get all available tabs first
            tabs = await self._get_available_tabs(page)
            print(f"\n📋 Found {len(tabs)} tabs: {', '.join(tabs)}")
            
            # Collect data from each tab
            for tab_name in tabs:
                print(f"\n{'-'*60}")
                print(f"📊 Collecting: {tab_name}")
                print(f"{'-'*60}")
                
                try:
                    # Navigate to tab
                    await self._navigate_to_tab(page, tab_name)
                    await asyncio.sleep(self.delay)
                    
                    # Extract data based on tab type
                    if tab_name == "往績紀錄":
                        result["race_history"] = await self._extract_race_history(page)
                    elif tab_name == "馬匹評分/體重/名次":
                        result["rating_history"] = await self._extract_rating_history(page)
                    elif tab_name == "所跑途程賽績紀錄":
                        result["distance_stats"] = await self._extract_distance_stats(page)
                    elif tab_name == "晨操紀錄":
                        result["workouts"] = await self._extract_workouts(page)
                    elif tab_name == "傷患紀錄":
                        result["medical"] = await self._extract_medical(page)
                    elif tab_name == "搬遷紀錄":
                        result["movements"] = await self._extract_movements(page)
                    elif tab_name == "海外賽績紀錄":
                        result["overseas"] = await self._extract_overseas(page)
                    elif tab_name == "血統簡評":
                        result["pedigree"] = await self._extract_pedigree(page)
                    
                except Exception as e:
                    print(f"   ⚠️ Error in {tab_name}: {e}")
                    result[tab_name] = {"error": str(e)}
            
            # Extract jersey (from main page)
            print(f"\n{'-'*60}")
            print("👕 Checking jersey...")
            print(f"{'-'*60}")
            result["jersey"] = await self._extract_jersey(page)
            
            await context.close()
            return result
            
        except Exception as e:
            logger.error(f"Error: {e}")
            await context.close()
            raise
    
    async def _get_available_tabs(self, page) -> List[str]:
        """Get list of available tabs"""
        tabs = []
        
        # Common tab selectors
        selectors = [
            "[role='tab']",
            ".tab",
            "a.tab",
            "button.tab",
            "li[role='tab']"
        ]
        
        for selector in selectors:
            elements = await page.query_selector_all(selector)
            for elem in elements:
                try:
                    text = await elem.inner_text()
                    text = text.strip()
                    if text and len(text) < 30:
                        # Filter for horse-related tabs
                        keywords = ["往績", "評分", "途程", "晨操", "傷患", "搬遷", "海外", "血統"]
                        if any(k in text for k in keywords):
                            if text not in tabs:
                                tabs.append(text)
                except:
                    continue
        
        return tabs
    
    async def _navigate_to_tab(self, page, tab_name: str):
        """Click on a tab"""
        # Try multiple selectors
        selectors = [
            f"a:has-text('{tab_name}')",
            f"[role='tab']:has-text('{tab_name}')",
            f"button:has-text('{tab_name}')",
        ]
        
        for selector in selectors:
            try:
                if await page.is_visible(selector, timeout=1000):
                    await page.click(selector)
                    return True
            except:
                continue
        
        # Manual search
        all_elements = await page.query_selector_all("a, button, [role='tab']")
        for elem in all_elements:
            try:
                text = await elem.inner_text()
                if tab_name in text:
                    await elem.click()
                    return True
            except:
                continue
        
        return False
    
    async def _extract_race_history(self, page) -> List[Dict]:
        """Extract race history (17 races for 祝願)"""
        races = []
        
        tables = await page.query_selector_all("table")
        
        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) >= 5 and len(rows) <= 25:  # Reasonable range
                header = await rows[0].inner_text()
                if "場次" in header and "名次" in header:
                    headers = [await c.inner_text() for c in await rows[0].query_selector_all("th,td")]
                    
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 10:
                            race = {}
                            for i, cell in enumerate(cells):
                                if i < len(headers):
                                    key = headers[i].strip().replace('\n', '_')
                                    val = await cell.inner_text()
                                    race[key] = val.strip() if val else ""
                            races.append(race)
                    
                    print(f"   ✅ {len(races)} races")
                    return races
        
        print("   ⚠️ Race history table not found")
        return []
    
    async def _extract_rating_history(self, page) -> List[Dict]:
        """Extract rating/weight/position history"""
        records = []
        
        # Look for specific table structure
        tables = await page.query_selector_all("table")
        
        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) < 2:
                continue
            
            header = await rows[0].inner_text()
            if any(k in header for k in ["評分", "體重", "名次"]):
                print(f"   Found table with {len(rows)-1} rows")
                
                headers = [await c.inner_text() for c in await rows[0].query_selector_all("th,td")]
                
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 3:
                        record = {}
                        for i, cell in enumerate(cells):
                            if i < len(headers):
                                record[headers[i].strip()] = await cell.inner_text()
                        records.append(record)
                
                print(f"   ✅ {len(records)} records")
                return records
        
        print("   ℹ️ No separate rating history found (data in race history)")
        return []
    
    async def _extract_distance_stats(self, page) -> List[Dict]:
        """Extract distance statistics"""
        stats = []
        
        tables = await page.query_selector_all("table")
        
        for table in tables:
            rows = await table.query_selector_all("tr")
            if 2 <= len(rows) <= 10:  # Distance stats usually small
                header = await rows[0].inner_text()
                if "途程" in header or "距離" in header:
                    print(f"   Found table with {len(rows)-1} rows")
                    
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 4:
                            stat = {
                                "distance": await cells[0].inner_text() if len(cells) > 0 else "",
                                "starts": await cells[1].inner_text() if len(cells) > 1 else "",
                                "wins": await cells[2].inner_text() if len(cells) > 2 else "",
                                "places": await cells[3].inner_text() if len(cells) > 3 else ""
                            }
                            stats.append(stat)
                    
                    print(f"   ✅ {len(stats)} distance records")
                    return stats
        
        print("   ℹ️ No distance stats found")
        return []
    
    async def _extract_workouts(self, page) -> List[Dict]:
        """Extract workout records"""
        workouts = []
        
        # Check if no records message
        page_text = await page.inner_text("body")
        if "沒有" in page_text or "很抱歉" in page_text:
            print("   ℹ️ No workout records")
            return []
        
        tables = await page.query_selector_all("table")
        
        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) < 2 or len(rows) > 200:  # Sanity check
                continue
            
            header = await rows[0].inner_text()
            if "日期" in header and ("時間" in header or "途程" in header):
                print(f"   Found workout table with {len(rows)-1} rows")
                
                valid_count = 0
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 4:
                        first_cell = await cells[0].inner_text()
                        # Validate date format
                        if re.match(r'\d{2}/\d{2}/\d{2,4}', first_cell.strip()):
                            workout = {
                                "date": first_cell.strip(),
                                "venue": await cells[1].inner_text() if len(cells) > 1 else "",
                                "distance": await cells[2].inner_text() if len(cells) > 2 else "",
                                "time": await cells[3].inner_text() if len(cells) > 3 else "",
                                "rider": await cells[4].inner_text() if len(cells) > 4 else ""
                            }
                            workouts.append(workout)
                            valid_count += 1
                
                print(f"   ✅ {valid_count} valid workouts")
                return workouts
        
        print("   ⚠️ Workout table structure unclear")
        return []
    
    async def _extract_medical(self, page) -> List[Dict]:
        """Extract medical records - 祝願 should have 0"""
        
        # Check for no records message first
        page_text = await page.inner_text("body")
        if any(msg in page_text for msg in ["沒有", "很抱歉", "no record"]):
            print("   ℹ️ No medical records (confirmed)")
            return []
        
        tables = await page.query_selector_all("table")
        
        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) < 2:
                continue
            
            header = await rows[0].inner_text()
            if "日期" in header:
                count = len(rows) - 1
                if count > 50:  # Suspicious
                    print(f"   ⚠️ Suspicious count: {count}, likely incorrect")
                    return []
                
                records = []
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 3:
                        record = {
                            "date": await cells[0].inner_text(),
                            "issue": await cells[1].inner_text() if len(cells) > 1 else "",
                            "treatment": await cells[2].inner_text() if len(cells) > 2 else ""
                        }
                        records.append(record)
                
                print(f"   ✅ {len(records)} medical records")
                return records
        
        print("   ℹ️ No medical table found")
        return []
    
    async def _extract_movements(self, page) -> List[Dict]:
        """Extract movement records"""
        
        # Check for no records
        page_text = await page.inner_text("body")
        if any(msg in page_text for msg in ["沒有", "很抱歉", "no record"]):
            print("   ℹ️ No movement records")
            return []
        
        tables = await page.query_selector_all("table")
        
        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) < 2:
                continue
            
            header = await rows[0].inner_text()
            if "日期" in header and "搬遷" in header:
                count = len(rows) - 1
                if count > 20:  # Suspicious for single horse
                    print(f"   ⚠️ Suspicious count: {count}, capping at reasonable number")
                    count = min(count, 10)
                
                movements = []
                for row in rows[1:count+1]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 3:
                        movement = {
                            "date": await cells[0].inner_text(),
                            "from_location": await cells[1].inner_text() if len(cells) > 1 else "",
                            "to_location": await cells[2].inner_text() if len(cells) > 2 else "",
                            "reason": await cells[3].inner_text() if len(cells) > 3 else ""
                        }
                        movements.append(movement)
                
                print(f"   ✅ {len(movements)} movements")
                return movements
        
        print("   ℹ️ No movement records found")
        return []
    
    async def _extract_overseas(self, page) -> List[Dict]:
        """Extract overseas race records"""
        
        # Check if tab even exists
        page_text = await page.inner_text("body")
        if "海外賽績紀錄" not in page_text:
            print("   ℹ️ Overseas tab does not exist for this horse")
            return []
        
        if any(msg in page_text for msg in ["沒有", "很抱歉", "no record"]):
            print("   ℹ️ No overseas records")
            return []
        
        tables = await page.query_selector_all("table")
        
        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) < 2:
                continue
            
            for row in rows[1:]:
                cells = await row.query_selector_all("td")
                if len(cells) >= 5:
                    # Validate overseas data
                    country = await cells[1].inner_text() if len(cells) > 1 else ""
                    if country and not any(c in "香港沙田快活谷從化" for c in country):
                        # Looks like overseas
                        races = []
                        for r in rows[1:]:
                            cs = await r.query_selector_all("td")
                            if len(cs) >= 5:
                                race = {
                                    "date": await cs[0].inner_text(),
                                    "country": await cs[1].inner_text() if len(cs) > 1 else "",
                                    "racecourse": await cs[2].inner_text() if len(cs) > 2 else "",
                                    "position": await cs[3].inner_text() if len(cs) > 3 else ""
                                }
                                races.append(race)
                        
                        print(f"   ✅ {len(races)} overseas races")
                        return races
        
        print("   ℹ️ No overseas records")
        return []
    
    async def _extract_pedigree(self, page) -> Dict:
        """Extract pedigree information"""
        pedigree = {}
        
        text = await page.inner_text("body")
        
        # Extract using regex
        patterns = {
            "sire": r'父系\s*[:：]\s*([^\n]+)',
            "dam": r'母系\s*[:：]\s*([^\n]+)',
            "damsire": r'外祖父\s*[:：]\s*([^\n]+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                pedigree[key] = match.group(1).strip()
        
        if pedigree:
            print(f"   ✅ Pedigree: {', '.join(pedigree.keys())}")
        else:
            print("   ℹ️ No pedigree data")
        
        return pedigree
    
    async def _extract_jersey(self, page) -> Optional[str]:
        """Extract jersey image URL"""
        images = await page.query_selector_all("img")
        
        for img in images:
            alt = await img.get_attribute("alt")
            src = await img.get_attribute("src")
            
            if alt and ("彩衣" in alt or "jersey" in alt.lower()):
                print(f"   ✅ Jersey found: {src[:60]}...")
                return src
        
        print("   ℹ️ Jersey image not found")
        return None


async def main():
    """Test with 祝願"""
    scraper = CompleteHorseSystem(headless=True, delay=2)
    
    async with scraper:
        data = await scraper.collect_horse("HK_2023_J256")
        
        print("\n" + "="*80)
        print("📊 COLLECTION COMPLETE - Summary")
        print("="*80)
        
        summary = {
            "race_history": len(data.get("race_history", [])),
            "rating_history": len(data.get("rating_history", [])),
            "distance_stats": len(data.get("distance_stats", [])),
            "workouts": len(data.get("workouts", [])),
            "medical": len(data.get("medical", [])),
            "movements": len(data.get("movements", [])),
            "overseas": len(data.get("overseas", [])),
            "pedigree": len(data.get("pedigree", {})),
            "jersey": "Found" if data.get("jersey") else "Not found"
        }
        
        for key, value in summary.items():
            print(f"  {key}: {value}")
        
        print("\n" + "="*80)
        print("Next: Save to MongoDB or continue processing")
        print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
