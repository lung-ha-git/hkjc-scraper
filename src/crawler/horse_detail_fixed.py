"""
HKJC Horse Detail Scraper - Fixed Version v2
Parse horse details from HKJC horse page
"""

import asyncio
import re
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright
from datetime import datetime
from typing import Dict, List
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection


class HorseDetailScraper:
    """Scrape horse details from HKJC"""
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse"
    
    def __init__(self, headless: bool = True, delay: int = 2):
        self.headless = headless
        self.delay = delay
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def scrape_horse(self, horse_id: str) -> Dict:
        """Scrape horse details"""
        url = f"{self.BASE_URL}?horseid={horse_id}"
        
        print(f"\n🐴 Scraping: {horse_id}")
        print("=" * 60)
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(self.delay)
            
            # Get full page text
            text = await page.inner_text("body")
            
            # Extract basic info
            horse_info = await self._extract_basic_info(page, horse_id)
            
            # Get all tables
            tables = await page.query_selector_all("table")
            print(f"📊 Found {len(tables)} tables")
            
            # Extract data
            race_history = await self._extract_race_history(tables, horse_id)
            print(f"🏇 Race History: {len(race_history)} races")
            
            workouts = await self._extract_workouts(tables, horse_id)
            print(f"🌅 Workouts: {len(workouts)} records")
            
            medical = await self._extract_medical(text)
            print(f"🩸 Medical: {medical} records")
            
            movements = await self._extract_movements(tables, horse_id)
            print(f"🚚 Movements: {len(movements)} records")
            
            distance_stats = await self._extract_distance_stats(tables, horse_id)
            print(f"📏 Distance Stats: {len(distance_stats)} records")
            
            await context.close()
            
            return {
                "hkjc_horse_id": horse_id,
                "horse_name": horse_info.get("name", ""),
                "basic_info": horse_info,
                "race_history": race_history,
                "workouts": workouts,
                "medical": medical,
                "movements": movements,
                "distance_stats": distance_stats,
                "url": url,
                "scraped_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error: {e}")
            await context.close()
            raise
    
    async def _extract_basic_info(self, page, horse_id: str) -> Dict:
        """Extract basic horse info"""
        text = await page.inner_text("body")
        
        info = {"hkjc_horse_id": horse_id}
        
        # Name
        name_match = re.search(r'^([^\n(]+)', text)
        if name_match:
            info["name"] = name_match.group(1).strip()
        
        # Birthplace and age
        bp_match = re.search(r'出生地\s*/\s*馬齡\s*[:：]\s*([^\n/]+)\s*/\s*(\d+)', text)
        if bp_match:
            info["birthplace"] = bp_match.group(1).strip()
            info["age"] = int(bp_match.group(2))
        
        # Color and sex
        color_match = re.search(r'毛色\s*/\s*性別\s*[:：]\s*([^\n/]+)\s*/\s*([^\n]+)', text)
        if color_match:
            info["color"] = color_match.group(1).strip()
            info["sex"] = color_match.group(2).strip()
        
        # Trainer
        trainer_match = re.search(r'練馬師\s*[:：]\s*([^\n]+)', text)
        if trainer_match:
            info["trainer"] = trainer_match.group(1).strip()
        
        # Owner
        owner_match = re.search(r'馬主\s*[:：]\s*([^\n]+)', text)
        if owner_match:
            info["owner"] = owner_match.group(1).strip()
        
        # Current rating
        rating_match = re.search(r'現時評分\s*[:：]\s*(\d+)', text)
        if rating_match:
            info["current_rating"] = int(rating_match.group(1))
        
        # Sire
        sire_match = re.search(r'父系\s*[:：]\s*([^\n]+)', text)
        if sire_match:
            info["sire"] = sire_match.group(1).strip()
        
        # Dam
        dam_match = re.search(r'母系\s*[:：]\s*([^\n]+)', text)
        if dam_match:
            info["dam"] = dam_match.group(1).strip()
        
        # Dam sire
        damsire_match = re.search(r'外祖父\s*[:：]\s*([^\n]+)', text)
        if damsire_match:
            info["dam_sire"] = damsire_match.group(1).strip()
        
        # Win/Place record
        record_match = re.search(r'冠-亞-季-總出賽次數[*]?\s*[:：]\s*(\d+)-(\d+)-(\d+)-(\d+)', text)
        if record_match:
            info["wins"] = int(record_match.group(1))
            info["seconds"] = int(record_match.group(2))
            info["thirds"] = int(record_match.group(3))
            info["total_runs"] = int(record_match.group(4))
        
        return info
    
    async def _extract_race_history(self, tables, horse_id: str) -> List[Dict]:
        """Extract race history from bigborder table"""
        races = []
        
        for table in tables:
            class_attr = await table.get_attribute("class") or ""
            
            if "bigborder" not in class_attr:
                continue
            
            rows = await table.query_selector_all("tr")
            
            if len(rows) < 2:
                continue
            
            # Check header
            header_text = await rows[0].inner_text()
            
            if "場次" not in header_text:
                continue
            
            # Extract data rows
            for row in rows[1:]:
                cells = await row.query_selector_all("td")
                
                if len(cells) < 5:
                    continue
                
                first_cell_text = await cells[0].inner_text()
                first_cell_text = first_cell_text.strip()
                
                # Skip season separator rows
                if "馬季" in first_cell_text or not first_cell_text:
                    continue
                
                if not re.match(r'^\d+$', first_cell_text):
                    continue
                
                race = {
                    "hkjc_horse_id": horse_id,
                    "race_no": first_cell_text,
                    "position": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                    "date": (await cells[2].inner_text()).strip() if len(cells) > 2 else "",
                    "venue": (await cells[3].inner_text()).strip() if len(cells) > 3 else "",
                    "distance": (await cells[4].inner_text()).strip() if len(cells) > 4 else "",
                }
                
                if len(cells) > 8:
                    race["rating"] = (await cells[8].inner_text()).strip()
                
                if len(cells) > 10:
                    race["jockey"] = (await cells[10].inner_text()).strip()
                
                # Extract race result URL from link
                links = await row.query_selector_all("a[href*='localresults']")
                if links:
                    href = await links[0].get_attribute("href")
                    race["race_url"] = "https://racing.hkjc.com" + href
                    
                    # Parse URL parameters
                    date_match = re.search(r'racedate=([^&]+)', href)
                    course_match = re.search(r'Racecourse=([^&]+)', href)
                    no_match = re.search(r'RaceNo=(\d+)', href)
                    
                    if date_match:
                        race["race_date"] = date_match.group(1)
                    if course_match:
                        race["race_course"] = course_match.group(1)
                    if no_match:
                        race["race_no"] = int(no_match.group(1))
                
                races.append(race)
            
            print(f"   ✅ Extracted {len(races)} races")
            break
        
        return races
    
    async def _extract_workouts(self, tables, horse_id: str) -> List[Dict]:
        """Extract workouts from table_bd"""
        workouts = []
        
        for table in tables:
            class_attr = await table.get_attribute("class") or ""
            
            if "table_bd" in class_attr:
                rows = await table.query_selector_all("tr")
                
                if len(rows) < 2:
                    continue
                
                header = await rows[0].inner_text()
                
                if "日期" in header and ("時間" in header or "晨操" in header):
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        
                        if len(cells) >= 2:
                            workout = {
                                "hkjc_horse_id": horse_id,
                                "date": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                                "details": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                            }
                            workouts.append(workout)
                    
                    if workouts:
                        print(f"   ✅ Extracted {len(workouts)} workouts")
                    break
        
        return workouts
    
    async def _extract_medical(self, text: str) -> int:
        """Check if medical records exist"""
        if "沒有" in text and "傷患" in text:
            if "傷患紀錄" in text:
                sections = text.split("傷患紀錄")
                if len(sections) > 1:
                    section = sections[1][:200]
                    if "沒有" in section or "找不到資料" in section:
                        return 0
        
        return 0
    
    async def _extract_movements(self, tables, horse_id: str) -> List[Dict]:
        """Extract movements"""
        movements = []
        
        for table in tables:
            table_id = await table.get_attribute("id") or ""
            
            if "MovementRecord" in table_id:
                rows = await table.query_selector_all("tr")
                
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    
                    if len(cells) >= 2:
                        movement = {
                            "hkjc_horse_id": horse_id,
                            "date": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                            "details": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                        }
                        movements.append(movement)
                
                if movements:
                    print(f"   ✅ Extracted {len(movements)} movements")
                break
        
        return movements
    
    async def _extract_distance_stats(self, tables, horse_id: str) -> List[Dict]:
        """Extract distance stats"""
        stats = []
        
        for table in tables:
            class_attr = await table.get_attribute("class") or ""
            
            if "horseperformance" in class_attr:
                rows = await table.query_selector_all("tr")
                
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    
                    if len(cells) >= 3:
                        stat = {
                            "hkjc_horse_id": horse_id,
                            "distance": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                            "wins": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                            "details": (await cells[2].inner_text()).strip() if len(cells) > 2 else "",
                        }
                        stats.append(stat)
                
                if stats:
                    print(f"   ✅ Extracted {len(stats)} distance stats")
                break
        
        return stats
    
    async def save_to_mongodb(self, data: Dict):
        """Save to MongoDB"""
        print("\n💾 Saving to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            print("❌ Cannot connect to MongoDB")
            return
        
        horse_id = data["hkjc_horse_id"]
        
        # Save basic info
        db.db["horses"].replace_one(
            {"hkjc_horse_id": horse_id},
            data["basic_info"],
            upsert=True
        )
        
        # Save race history
        db.db["horse_race_history"].delete_many({"hkjc_horse_id": horse_id})
        if data["race_history"]:
            db.db["horse_race_history"].insert_many(data["race_history"])
        
        # Save workouts
        db.db["horse_workouts"].delete_many({"hkjc_horse_id": horse_id})
        if data["workouts"]:
            db.db["horse_workouts"].insert_many(data["workouts"])
        
        # Save medical count
        db.db["horse_medical"].delete_many({"hkjc_horse_id": horse_id})
        db.db["horse_medical"].insert_one({
            "hkjc_horse_id": horse_id,
            "count": data["medical"]
        })
        
        # Save movements
        db.db["horse_movements"].delete_many({"hkjc_horse_id": horse_id})
        if data["movements"]:
            db.db["horse_movements"].insert_many(data["movements"])
        
        # Save distance stats
        db.db["horse_distance_stats"].delete_many({"hkjc_horse_id": horse_id})
        if data["distance_stats"]:
            db.db["horse_distance_stats"].insert_many(data["distance_stats"])
        
        db.disconnect()
        print("✅ Done!")


async def main():
    """Test with 氣勢"""
    async with HorseDetailScraper(headless=True, delay=3) as scraper:
        data = await scraper.scrape_horse("HK_2022_H411")
        
        print("\n" + "=" * 60)
        print("📊 RESULTS")
        print("=" * 60)
        print(f"Horse: {data['horse_name']} ({data['hkjc_horse_id']})")
        print(f"Trainer: {data['basic_info'].get('trainer', 'N/A')}")
        print(f"Race History: {len(data['race_history'])} races")
        print(f"Workouts: {len(data['workouts'])} records")
        print(f"Medical: {data['medical']}")
        print(f"Movements: {len(data['movements'])}")
        
        # Show sample races
        if data['race_history']:
            print("\n🏇 Sample Races:")
            for r in data['race_history'][:3]:
                print(f"  {r['date']} | {r['venue']} | {r['distance']} | 第{r['position']}名 | {r.get('jockey', 'N/A')}")
        
        # Save
        await scraper.save_to_mongodb(data)


if __name__ == "__main__":
    asyncio.run(main())
